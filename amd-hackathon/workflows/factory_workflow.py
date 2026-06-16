# workflows/factory_workflow.py
import warnings
warnings.filterwarnings("ignore", category=UserWarning)
import inspect
import json
import re

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

# CCTV scene description agent - optional, falls back to vision_out
try:
    from agents.scene_description_agent import agent as scene_agent
except ImportError:
    try:
        from agents.scene_description_agent.scene_description_agent import agent as scene_agent
    except Exception:
        scene_agent = None

from tools.kpi_tools import log_kpi_live

# ------------------------------------------------------------------
# 0. Decision router – PPE / helmet aware
# ------------------------------------------------------------------
def decision_router(vision_out: str, telemetry_out: str, safety_out: str) -> str:
    text = f"{vision_out} {telemetry_out} {safety_out}".upper()
    # critical
    if any(k in text for k in ["OVERHEAT", "FAILURE_ALERT", "CRITICAL", "SHUTDOWN", "TEMPERATURE", "BURN"]):
        return "critical_maintenance"
    # safety – PPE / helmet / glove / vest
    if any(k in text for k in [
        "SAFETY_ALERT", "HELMET", "HARD_HAT", "GLOVE", "VEST",
        "PPE", "NO_PPE", "MISSING", "FALL", "UNSAFE"
    ]):
        return "safety_violation"
    # quality
    if any(k in text for k in [
        "DEFECT_ALERT", "DEFECT", "ANOMALY",
        "OVERSPEED", "PRESSURE", "RPM", "FLAG",
        "UNSTABLE", "VIBRATION"
    ]):
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
                _live_cache["error_code"] = d.get("error_code", "OK")
    except Exception:
        pass
    return _live_cache["vibration"], _live_cache["temperature"], _live_cache["error_code"]

# ------------------------------------------------------------------
# 2. Streaming-safe agent wrapper
# ------------------------------------------------------------------
_sensor_context = {"vision": "", "telemetry": "", "safety": ""}

def _event_to_text(event) -> str:
    """Extract text from AgentRunResponse / ResponseStream / str – DevUI safe."""
    if event is None:
        return ""
    if isinstance(event, str):
        return event
    for attr in ("text", "content", "message", "output", "value"):
        if hasattr(event, attr):
            value = getattr(event, attr)
            if value is not None and value is not event:
                t = _event_to_text(value)
                if t:
                    return t
    return str(event)

async def _run_agent(agent, prompt: str) -> str:
    """Consume an agent whether its run() is coroutine or async generator. Returns last string."""
    result = agent.run(prompt)
    if inspect.isawaitable(result):
        return _event_to_text(await result)
    last = ""
    if hasattr(result, "__aiter__"):
        async for event in result:
            text = _event_to_text(event)
            if text:
                last = text
        return last
    return _event_to_text(result)

def _make_streaming(agent, kind: str | None = None):
    # Keep framework agents untouched – monkey-patching agent.run breaks
    # Agent Framework event metadata (user_input_requests) in 1.0.0b260528
    return agent

_make_streaming(defect_agent, "defect")
_make_streaming(telemetry_agent, "telemetry")
_make_streaming(safety_agent, "safety")
_make_streaming(orchestrator_agent, None)
if scene_agent:
    _make_streaming(scene_agent, None)

# ------------------------------------------------------------------
# 3. DecisionRouter workflow node
# NOTE: do NOT wrap agent.run here – any yield of a non-AgentRunResponse
# object causes: Workflow execution error: 'ResponseStream' object has no attribute 'user_input_requests'
# in agent_framework 1.0.0b260528
# ------------------------------------------------------------------
decision_router_agent = None
try:
    from agent_framework import Executor
    decision_router_agent = Executor(id="decision_router_node")

    @decision_router_agent.handler
    async def decide_handler(input_msg: str = "", **kwargs):
        vision = _sensor_context.get("vision", "")
        telemetry = _sensor_context.get("telemetry", "")
        safety = _event_to_text(input_msg) if input_msg else _sensor_context.get("safety", "")
        return decision_router(vision, telemetry, safety)
except Exception:
    import copy
    decision_router_agent = copy.copy(orchestrator_agent)

_make_streaming(decision_router_agent, None)
# decision_router_agent.run is NOT wrapped – see note above

# ------------------------------------------------------------------
# 4. Factory cycle, used by main.py – PPE prompt forces SAFETY_ALERT
# ------------------------------------------------------------------
async def run_factory_cycle(p):
    vision_out = await _run_agent(defect_agent,
        f"Detected: {p.input_detected_objects}\n"
        f"If defect found, respond with: DEFECT_ALERT: <description> else CLEAR"
    )
    _sensor_context["vision"] = str(vision_out)

    telemetry_out = await _run_agent(telemetry_agent,
        f"Vibration={p.input_vibration}mm/s, Temp={p.input_temp}C\n"
        f"If vibration > 8 or temp > 80, respond: OVERHEAT_ALERT / ANOMALY_ALERT else NORMAL"
    )
    _sensor_context["telemetry"] = str(telemetry_out)

    # SafetyAgent: explicit PPE check – forces SAFETY_ALERT prefix
    safety_prompt = (
        f"detected_objects: {p.input_detected_objects}\n"
        f"Task: Check PPE compliance – helmet / hard_hat, gloves, safety_vest.\n"
        f"If any PPE is missing, respond EXACTLY: SAFETY_ALERT: <missing_items>\n"
        f"else respond: CLEAR"
    )
    safety_out = await _run_agent(safety_agent, safety_prompt)

    # --- parse SafetyAgent output ---
    safety_text = str(safety_out).strip()
    is_alert = "SAFETY_ALERT" in safety_text.upper()

    # PPE extraction – helmet / hard_hat / glove / vest
    ppe_missing = []
    low = safety_text.lower()
    if any(k in low for k in ["helmet", "hard_hat", "no_helmet", "missing_helmet"]):
        ppe_missing.append("helmet")
    if "glove" in low:
        ppe_missing.append("gloves")
    if "vest" in low:
        ppe_missing.append("safety_vest")
    if is_alert and not ppe_missing:
        ppe_missing.append("ppe_kit")

    # Falling risk score 0-100
    falling_risk_score = int(min(100, max(0, p.input_vibration * 8 + p.input_temp * 0.15)))
    if is_alert or ppe_missing:
        falling_risk_score = min(100, falling_risk_score + 25)

    # --- FALLING RISK SAFETY FLAG >85 ---
    if falling_risk_score > 85:
        is_alert = True
        if "SAFETY_ALERT" not in safety_text.upper():
            safety_text = f"SAFETY_ALERT: Falling risk {falling_risk_score} - {safety_text}"
        else:
            safety_text = f"{safety_text} | Falling risk {falling_risk_score}"
        safety_out = safety_text

    _sensor_context["safety"] = str(safety_out)

    # Accident prediction score 0-100
    accident_prediction_score = falling_risk_score // 2
    if is_alert:
        accident_prediction_score += 30
    if ppe_missing:
        accident_prediction_score += len(ppe_missing) * 10
    accident_prediction_score = max(0, min(100, accident_prediction_score))

    safety_description = safety_text if safety_text else "CLEAR"
    ppe_violations_str = ",".join(ppe_missing)

    # --- CCTV scene description ---
    if scene_agent:
        scene_out = await _run_agent(scene_agent,
            f"objects={p.input_detected_objects}, vibration={p.input_vibration}, temp={p.input_temp}, machine={p.machine_id}"
        )
        video_description = str(scene_out).strip()[:500]
    else:
        video_description = str(vision_out)[:200]

    decision = decision_router(str(vision_out), str(telemetry_out), str(safety_out))
    action, downtime, defects, safety = ACTION_MAP[decision]

    if decision!= "normal":
        await _run_agent(orchestrator_agent, f"{decision} on {p.machine_id}. Execute {action}. Safety: {safety_description}")

    log_kpi_live(
        input_vibration=p.input_vibration,
        input_temp=p.input_temp,
        input_detected_objects=p.input_detected_objects,
        video_description=video_description,
        agent_decision=decision,
        alert_type=f"{vision_out} {telemetry_out} {safety_out}"[:120],
        action_taken=action,
        machine_id=p.machine_id,
        downtime_saved_hrs=downtime,
        defects_caught=defects,
        safety_violations=safety,
        safety_description=safety_description,
        falling_risk_score=falling_risk_score,
        accident_prediction_score=accident_prediction_score,
        ppe_violations=ppe_violations_str,
    )
    return decision, action

# ------------------------------------------------------------------
# 5. WorkflowBuilder
# Action nodes are NOT wrapped – wrapping causes ResponseStream / user_input_requests crash
# in agent_framework 1.0.0b260528. Hallucination in Dev UI output text is the tradeoff
# for a crash-free workflow. run_factory_cycle() uses the deterministic python router.
# ------------------------------------------------------------------
def _clone_action(base, name):
    import copy
    a = copy.copy(base)
    for attr in ("name", "_name", "id", "display_name"):
        if hasattr(a, attr):
            try: setattr(a, attr, name)
            except Exception: pass
    # DO NOT override a.run – see note above
    return a

def build_factory_workflow():
    from agent_framework import WorkflowBuilder
    action_normal = _clone_action(orchestrator_agent, "Action_Normal")
    action_critical = _clone_action(orchestrator_agent, "Action_CriticalMaintenance")
    action_safety = _clone_action(orchestrator_agent, "Action_SafetyViolation")
    action_quality = _clone_action(orchestrator_agent, "Action_QualityDefect")

    def _match(x, keys):
        t = _event_to_text(x).lower()
        return any(k in t for k in keys)

    try:
        builder = WorkflowBuilder(name="FactoryMonitor", start_executor=defect_agent)
        builder.add_chain([defect_agent, telemetry_agent, safety_agent, decision_router_agent])
        # broad matching – catches both "quality_defect" and "DECISION: OVERSPEED_ALERT / ACTION: flag_anomaly"
        builder.add_edge(decision_router_agent, action_critical,
            condition=lambda x: _match(x, ["critical_maintenance", "shutdown_conveyor", "overheat", "failure_alert", "critical"]))
        builder.add_edge(decision_router_agent, action_safety,
            condition=lambda x: _match(x, ["safety_violation", "notify_supervisor", "safety_alert", "helmet", "hard_hat", "ppe", "vest", "glove", "fall"]))
        builder.add_edge(decision_router_agent, action_quality,
            condition=lambda x: _match(x, ["quality_defect", "flag_anomaly", "defect", "anomaly", "overspeed", "pressure", "rpm", "unstable"]))
        # catch-all normal – must be last
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
    if scene_agent:
        entities.append(scene_agent)
    if factory_workflow is not None:
        entities.append(factory_workflow)
    print(f"Video: {LIVE_VIDEO_URL}")
    print(f"Telemetry: {LIVE_TELEMETRY_URL}")
    serve(entities=entities, host="127.0.0.1", port=8080)