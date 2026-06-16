# tools/kpi_tools.py
from agent_framework import tool
from typing import Annotated
from pydantic import Field
from datetime import datetime
from pathlib import Path
import csv

KPI_PATH = Path("factory_kpis.csv")

HEADERS = [
    "timestamp",
    "input_vibration", "input_temp", "input_detected_objects",
    "video_description",
    "agent_decision", "alert_type",
    "action_taken", "machine_id",
    "downtime_saved_hrs", "defects_caught", "safety_violations",
    "safety_description", "falling_risk_score", "accident_prediction_score", "ppe_violations"
]

def init_kpi_file():
    need_header = True
    if KPI_PATH.exists() and KPI_PATH.stat().st_size > 0:
        try:
            with open(KPI_PATH, 'r', encoding='utf-8') as f:
                first = next(csv.reader(f), [])
                if first == HEADERS:
                    need_header = False
        except Exception:
            need_header = True
    if need_header:
        with open(KPI_PATH, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(HEADERS)

init_kpi_file()

@tool(name="log_kpi_live", description="Write a live KPI row to CSV. Call after EVERY decision.")
def log_kpi_live(
    input_vibration: Annotated[float, Field(description="mm/s")],
    input_temp: Annotated[float, Field(description="°C")],
    input_detected_objects: Annotated[str, Field(description="e.g. person,no_helmet")],
    agent_decision: Annotated[str, Field(description="critical_maintenance / safety_violation / quality_defect / normal")],
    alert_type: Annotated[str, Field(description="ANOMALY_ALERT, SAFETY_ALERT, DEFECT_ALERT, NORMAL")],
    action_taken: Annotated[str, Field(description="shutdown_conveyor / notify_supervisor / flag_anomaly / none")],
    machine_id: Annotated[str, Field(description="Line_1 / Line_2")] = "Line_1",
    downtime_saved_hrs: float = 0.0,
    defects_caught: int = 0,
    safety_violations: int = 0,
    # new fields
    safety_description: Annotated[str, Field(description="Human readable safety event description")] = "",
    falling_risk_score: Annotated[int, Field(description="0-100 falling risk")] = 0,
    accident_prediction_score: Annotated[int, Field(description="0-100 accident prediction")] = 0,
    ppe_violations: Annotated[str, Field(description="comma separated missing PPE, e.g. helmet,gloves")] = "",
    video_description: Annotated[str, Field(description="Scene description – what is happening in the video")] = "",
) -> str:
    row = [
        datetime.now().isoformat(),
        input_vibration, input_temp, input_detected_objects,
        video_description,
        agent_decision, alert_type,
        action_taken, machine_id,
        downtime_saved_hrs, defects_caught, safety_violations,
        safety_description, falling_risk_score, accident_prediction_score, ppe_violations
    ]
    with open(KPI_PATH, 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow(row)
    return "kpi_logged"