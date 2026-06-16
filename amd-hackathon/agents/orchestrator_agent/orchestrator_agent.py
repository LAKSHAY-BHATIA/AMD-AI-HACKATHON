from agent_framework import Agent, tool
from typing import Annotated
from pydantic import Field
from config.config import create_client # OpenAIChatClient pointing to Qwen/Qwen2.5-VL

# --- Action tools - called by the Orchestrator ---
@tool(name="shutdown_conveyor", description="Emergency stop for conveyor belt. Use for OVERHEAT / FAILURE_ALERT")
def shutdown_conveyor(
    line_id: Annotated[str, Field(description="e.g. Line_1, Line_2")]
) -> str:
    return f"Line {line_id} stopped. Downtime saved: 2.5 hrs"

@tool(name="notify_supervisor", description="Send alert to plant supervisor. Use for SAFETY_ALERT")
def notify_supervisor(
    message: Annotated[str, Field(description="Alert text")],
    severity: Annotated[str, Field(description="high / medium / low")] = "high"
) -> str:
    return f"Supervisor notified: {severity} - {message}"

@tool(name="flag_anomaly", description="Open a defect ticket in the QA tracker. Use for DEFECT_ALERT")
def flag_anomaly(
    machine_id: Annotated[str, Field(description="e.g. Line_2")],
    issue: Annotated[str, Field(description="Defect description")]
) -> str:
    return f"ALERT: Defect ticket opened for {machine_id}. Reason: {issue}"

# --- OrchestratorAgent ---
orchestrator_agent = Agent(
    name="OrchestratorAgent",
    instructions="""You are Plant Manager / Decision Router.
Read alerts from DefectAnalysisAgent, TelemetryAgent, SafetyAgent.
Route:
- OVERHEAT / FAILURE_ALERT -> call shutdown_conveyor
- SAFETY_ALERT -> call notify_supervisor
- DEFECT_ALERT -> call flag_anomaly
- else -> take no action
Always call exactly ONE tool if alert is present, then output a summary:
decision=<critical_maintenance|safety_violation|quality_defect|normal>, action_taken=<tool_name>, machine_id=<id>""",
    client=create_client(),
    tools=[shutdown_conveyor, notify_supervisor, flag_anomaly],
    #tools=[]
)