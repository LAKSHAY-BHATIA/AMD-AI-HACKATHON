from tools.kpi_tools import log_kpi_live

def decision_router(state: dict) -> str:
    """
    Input state from the 3 analysis agents:
    state["vision_out"], state["telemetry_out"], state["safety_out"]
    + preprocessor fields: input_vibration, input_temp, input_detected_objects, machine_id
    """
    text = f"{state.get('vision_out','')} {state.get('telemetry_out','')} {state.get('safety_out','')}".upper()

    if "OVERHEAT" in text or "FAILURE_ALERT" in text:
        return "critical_maintenance"
    if "SAFETY_ALERT" in text:
        return "safety_violation"
    if "DEFECT_ALERT" in text:
        return "quality_defect"
    return "normal"

async def action_executor_node(state: dict, orchestrator_agent) -> dict:
    """
    5. Action Executor
    Calls the OrchestratorAgent with the routed alert,
    then logs to KPI_TrackerAgent / Excel
    """
    route = state["decision"]
    machine_id = state.get("machine_id", "Line_2")

    # Build prompt for the Orchestrator
    prompt_map = {
        "critical_maintenance": f"Telemetry alert on {machine_id}. Vibration={state['input_vibration']}mm/s, Temp={state['input_temp']}C. Shutdown required.",
        "safety_violation": f"Safety alert on {machine_id}. Detected: {state['input_detected_objects']}. Notify supervisor.",
        "quality_defect": f"Defect alert on {machine_id}. Detected: {state['input_detected_objects']}. Flag anomaly.",
        "normal": "All clear. No action."
    }

    action_taken = "none"
    downtime, defects, safety = 0.0, 0, 0
    alert_type = route

    if route!= "normal":
        result = await orchestrator_agent.run(prompt_map[route])
        # OrchestratorAgent will call the correct tool automatically
        action_taken = {
            "critical_maintenance": "shutdown_conveyor",
            "safety_violation": "notify_supervisor",
            "quality_defect": "flag_anomaly"
        }[route]

        if route == "critical_maintenance": downtime = 2.5
        if route == "quality_defect": defects = 1
        if route == "safety_violation": safety = 1

    # --- KPI_TrackerAgent - live Excel write ---
    # This is the green box at the bottom of your flowchart
    log_kpi_live(
        input_vibration=state["input_vibration"],
        input_temp=state["input_temp"],
        input_detected_objects=state["input_detected_objects"],
        agent_decision=route,
        alert_type=alert_type,
        action_taken=action_taken,
        machine_id=machine_id,
        downtime_saved_hrs=downtime,
        defects_caught=defects,
        safety_violations=safety
    )

    state["action_taken"] = action_taken
    return state