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