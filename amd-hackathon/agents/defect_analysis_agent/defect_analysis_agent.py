from typing import Annotated
from pydantic import Field
from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatCompletionClient

@tool(
    name="flag_anomaly",
    description="Logs a high-priority equipment defect flag in the system tracker. Call only on confirmed defect."
)
def flag_anomaly(
    machine_id: Annotated[str, Field(description="Factory line ID, e.g. 'Line_1', 'Line_2'")],
    issue: Annotated[str, Field(description="Defect reason with measured value, e.g. 'Vibration 8.7 mm/s > 8.0 threshold'")],
) -> str:
    """Logs the anomaly event."""
    return f"ALERT: Defect ticket opened for {machine_id}. Reason: {issue}"

agent = Agent(
    name="DefectAgent",
    instructions="""You are a quality assurance inspector.

Inputs: detected_objects, vibration_mm_s, temperature_c, machine_id

Decision rules:
1. Vision defect if detected_objects contains crack/defect/damaged -> DEFECT_ALERT
2. Telemetry defect if vibration > 8.0 mm/s -> FAILURE_ALERT
3. Telemetry defect if temperature > 90.0 °C -> OVERHEAT_ALERT
4. Else -> CLEAR

Tool policy:
- Call flag_anomaly exactly ONCE for DEFECT_ALERT / FAILURE_ALERT / OVERHEAT_ALERT
- Never call for CLEAR
- issue = "<ALERT_TYPE>: <value> > <threshold>"

Output, always:
DECISION: <DEFECT_ALERT|FAILURE_ALERT|OVERHEAT_ALERT|CLEAR>
REASON: <one sentence>
ACTION: <flag_anomaly|none>
""",
    client=OpenAIChatCompletionClient(
        model="Qwen/Qwen2.5-VL-7B-Instruct",
        api_key="EMPTY",
        base_url="http://localhost:8000/v1",
    ),
    tools=[flag_anomaly]
)