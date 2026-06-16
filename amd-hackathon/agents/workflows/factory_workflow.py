# workflows/factory_workflow.py
import warnings
warnings.filterwarnings("ignore", category=UserWarning)
import inspect

# ------------------------------------------------------------------
# Agents - robust imports
# ------------------------------------------------------------------
try:
    from agents.defect_analysis_agent import agent as defect_agent
except ImportError:
    from agents.defect_analysis_agent.defect_analysis_agent import agent as defect_agent

try:
    from agents.telemetry_agent import agent as telemetry_agent
except ImportError:
    from agents.telemetry_agent.telemetry_agent import agent as telemetry_agent

try:
    from agents.safety_agent import agent as safety_agent
except ImportError:
    from agents.safety_agent.safety_agent import agent as safety_agent

try:
    from agents.orchestrator_agent import orchestrator_agent
except ImportError:
    from agents.orchestrator_agent.orchestrator_agent import orchestrator_agent

from tools.kpi_tools import log_kpi_live

# ------------------------------------------------------------------
# 0. Decision router
# ------------------------------------------------------------------
def decision_router(vision_out: str, telemetry_out: str, safety_out: str) -> str:
    text = f"{vision_out} {telemetry_out} {safety_out}".upper()
    if "OVERHEAT" in text or "FAILURE_ALERT" in text:
        return "critical_maintenance"
    if "SAFETY_ALERT" in text:
        return "safety_violation"
    if "DEFECT_ALERT" in text:
        return "quality_defect"
    return "normal"

ACTION_MAP = {
    "critical_maintenance": ("shutdown_conveyor", 2.5, 0, 0),
    "safety_violation": ("notify_supervisor", 0.0, 0, 1),
    "quality_defect": ("flag_anomaly", 0.0, 1, 0),
    "normal": ("none", 0.0, 0, 0),
}

# ------------------------------------------------------------------
# 1. Live telemetry / video ingest - FastAPI
# ------------------------------------------------------------------
USE_LIVE_TELEMETRY = True
LIVE_TELEMETRY_URL = "http://localhost:8001/api/telemetry/poll"
LIVE_VIDEO_URL = "http://localhost:8001/api/video/stream"

_live_cache = {"vibration": 0.0, "temperature": 0.0, "rpm": 0, "pressure": 0.0, "error_code": "OK"}

async def _get_live_telemetry():
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            r = await client.get(LIVE_TELEMETRY_URL, timeout=1.0)
            if r.status_code == 200:
                d = r.json()
                _live_cache["vibration"] = float(d.get("vibration", 0))
                _live_cache["temperature"] = float(d.get("temperature", 0))
                _live_cache["rpm"] = d.get("rpm", 0)
                _live_cache["pressure"] = d.get("pressure", 0)
    except Exception:
        pass
    return _live_cache["vibration"], _live_cache["temperature"], _live_cache["error_code"]

# ------------------------------------------------------------------
# 2. Streaming-safe agent wrapper - fixes the 'async for requires __aiter__' error
# ------------------------------------------------------------------
_sensor_context = {"vision": "", "telemetry": "", "safety": ""}

async def _run_agent(agent, prompt: str) -> str:
    """Consume an agent whether its run() is coroutine or async generator. Returns last string."""
    result = agent.run(prompt)
    if inspect.isawaitable(result):
        return str(await result)
    last = ""
    async for event in result:
        last = event if isinstance(event, str) else str(event)
    return last

def _make_streaming(agent, kind: str | None = None):
    """Force agent.run to always be an async generator. Optionally inject live telemetry for sensor agents."""
    orig_run = agent.run
    async def streaming_run(input_data=None, **kwargs):
        # inject live telemetry for sensor nodes only
        if USE_LIVE_TELEMETRY and kind in ("defect", "telemetry", "safety"):
            try:
                v, t, o = await _get_live_telemetry()
                if kind == "telemetry":
                    input_data = f"Vibration={v}mm/s, Temp={t}C"
                elif kind == "defect":
                    input_data = f"Detected: {o}, video={LIVE_VIDEO_URL}"
                elif kind == "safety":
                    input_data = f"ppe_violation=False, reason={o}, objects=none"
            except Exception:
                pass

        # call original, normalize to async iterator
        try:
            result = orig_run(input_data, **kwargs)
        except Exception as e:
            yield f"ERROR: {e}"
            return

        last = None
        # await if it's a coroutine
        if inspect.isawaitable(result):
            try:
                result = await result
            except Exception:
                pass

        # stream if async iterable, else yield once
        if hasattr(result, "__aiter__"):
            async for event in result:
                last = event
                yield event
        else:
            last = result
            yield result

        # store sensor outputs for the decision router
        if kind:
            out_s = str(last) if last is not None else ""
            if kind == "defect":
                _sensor_context["vision"] = out_s
            elif kind == "telemetry":
                _sensor_context["telemetry"] = out_s
            elif kind == "safety":
                _sensor_context["safety"] = out_s
    agent.run = streaming_run
    return agent

# patch all workflow nodes to be streaming-compatible
_make_streaming(defect_agent, "defect")
_make_streaming(telemetry_agent, "telemetry")
_make_streaming(safety_agent, "safety")
_make_streaming(orchestrator_agent, None)

# ------------------------------------------------------------------
# 3. DecisionRouter workflow node
# ------------------------------------------------------------------
decision_router_agent = None
try:
    from agent_framework import Executor
    decision_router_agent = Executor(id="decision_router_node")

    @decision_router_agent.handler
    async def decide_handler(input_msg: str = "") -> str:
        vision = _sensor_context.get("vision", "")
        telemetry = _sensor_context.get("telemetry", "")
        safety = str(input_msg) if input_msg else _sensor_context.get("safety", "")
        return decision_router(vision, telemetry, safety)
except Exception:
    import copy
    decision_router_agent = copy.copy(orchestrator_agent)

# make sure the decision node is also streaming-compatible
_make_streaming(decision_router_agent, None)
# override its run to actually call decision_router
_orig_decision_run = decision_router_agent.run
async def _decision_run_wrapper(input_data=None, **kwargs):
    # consume the wrapped orchestrator output (discard it), then yield the real decision
    async for _ in _orig_decision_run(input_data, **kwargs):
        pass
    vision = _sensor_context.get("vision", "")
    telemetry = _sensor_context.get("telemetry", "")
    safety = str(input_data) if input_data else _sensor_context.get("safety", "")
    yield decision_router(vision, telemetry, safety)

# if the Executor version was created successfully, replace its run with the streaming router
if hasattr(decision_router_agent, "run"):
    decision_router_agent.run = _decision_run_wrapper

# ------------------------------------------------------------------
# 4. Factory cycle, used by main.py
# ------------------------------------------------------------------
async def run_factory_cycle(p):
    vision_out = await _run_agent(defect_agent, f"Detected: {p.input_detected_objects}")
    telemetry_out = await _run_agent(telemetry_agent, f"Vibration={p.input_vibration}mm/s, Temp={p.input_temp}C")
    safety_out = await _run_agent(safety_agent,
        f"ppe_violation={getattr(p, 'ppe_violation', False)}, "
        f"reason={getattr(p, 'ppe_reason', 'clear')}, "
        f"objects={p.input_detected_objects}"
    )
    decision = decision_router(str(vision_out), str(telemetry_out), str(safety_out))
    action, downtime, defects, safety = ACTION_MAP[decision]
    if decision!= "normal":
        await _run_agent(orchestrator_agent, f"{decision} on {p.machine_id}. Execute {action}")
    log_kpi_live(
        input_vibration=p.input_vibration,
        input_temp=p.input_temp,
        input_detected_objects=p.input_detected_objects,
        agent_decision=decision,
        alert_type=f"{vision_out} {telemetry_out} {safety_out}"[:80],
        action_taken=action,
        machine_id=p.machine_id,
        downtime_saved_hrs=downtime,
        defects_caught=defects,
        safety_violations=safety,
    )
    return decision, action

# ------------------------------------------------------------------
# 5. WorkflowBuilder
# ------------------------------------------------------------------
def _clone_action(base, name):
    import copy
    a = copy.copy(base)
    for attr in ("name", "_name", "id", "display_name"):
        if hasattr(a, attr):
            try: setattr(a, attr, name)
            except Exception: pass
    # make clones streaming-compatible too
    _make_streaming(a, None)
    return a

def build_factory_workflow():
    from agent_framework import WorkflowBuilder
    action_normal = _clone_action(orchestrator_agent, "Action_Normal")
    action_critical = _clone_action(orchestrator_agent, "Action_CriticalMaintenance")
    action_safety = _clone_action(orchestrator_agent, "Action_SafetyViolation")
    action_quality = _clone_action(orchestrator_agent, "Action_QualityDefect")
    try:
        builder = WorkflowBuilder(name="FactoryMonitor", start_executor=defect_agent)
        builder.add_chain([defect_agent, telemetry_agent, safety_agent, decision_router_agent])
        builder.add_edge(decision_router_agent, action_critical,
            condition=lambda x: "critical_maintenance" in str(x).lower())
        builder.add_edge(decision_router_agent, action_safety,
            condition=lambda x: "safety_violation" in str(x).lower())
        builder.add_edge(decision_router_agent, action_quality,
            condition=lambda x: "quality_defect" in str(x).lower())
        builder.add_edge(decision_router_agent, action_normal,
            condition=lambda x: True)
        wf = builder.build()
        print("[factory_workflow] built with real DecisionRouter node")
        return wf
    except Exception as e:
        print(f"[factory_workflow] branched build failed: {e}")
    builder = WorkflowBuilder(name="FactoryMonitor", start_executor=defect_agent)
    builder.add_chain([defect_agent, telemetry_agent, safety_agent, orchestrator_agent])
    return builder.build()

factory_workflow = None
try:
    factory_workflow = build_factory_workflow()
    print(f"[factory_workflow] built OK: {factory_workflow}")
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"[factory_workflow] WorkflowBuilder disabled: {e}")

# ------------------------------------------------------------------
# 6. Dev UI
# ------------------------------------------------------------------
if __name__ == "__main__":
    from agent_framework.devui import serve
    entities = [defect_agent, telemetry_agent, safety_agent, orchestrator_agent, decision_router_agent]
    if factory_workflow is not None:
        entities.append(factory_workflow)
    print(f"Video: {LIVE_VIDEO_URL}")
    print(f"Telemetry: {LIVE_TELEMETRY_URL}")
    serve(entities=entities, host="127.0.0.1", port=8080)