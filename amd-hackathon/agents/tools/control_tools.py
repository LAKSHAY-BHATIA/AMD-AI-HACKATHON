# tools/control_tools.py
from agent_framework import tool
from typing import Annotated
from pydantic import Field

@tool(name="shutdown_conveyor", description="Emergency stop for conveyor belt. Use for OVERHEAT or FAILURE_RISK.")
def shutdown_conveyor(
    line_id: Annotated[str, Field(description="e.g. Line_2")]
) -> str:
    return f"Line {line_id} stopped. Downtime saved: 2.5 hrs"

@tool(name="notify_supervisor", description="Send alert to plant supervisor via Teams/Slack.")
def notify_supervisor(
    message: Annotated[str, Field(description="Alert text")],
    severity: Annotated[str, Field(description="high, medium, low")] = "high"
) -> str:
    print(f"[SUPERVISOR {severity.upper()}] {message}")
    return f"Alert sent: {severity} - {message}"