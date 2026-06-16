from typing import Annotated
from pydantic import Field
from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatCompletionClient

@tool(
    name="get_telemetry_logs",
    description="Fetches raw performance logs from manufacturing equipment. Call when you need current vibration, temperature, rpm, pressure for a machine."
)
def get_telemetry_logs(
    machine_id: Annotated[str, Field(description="Factory line ID, e.g. 'Line_1', 'Line_2', 'MCH-401'")]
) -> str:
    """Simulates reading machine log registers. Returns JSON with temp_C, vibration_mm_s, rpm, pressure_bar, status."""
    # replace with real MQTT/OPC-UA read
    # keeping your original values as fallback for the demo
    return f'{{"machine_id": "{machine_id}", "temperature_C": 85.0, "vibration_mm_s": 6.2, "rpm": 1500, "pressure_bar": 2.8, "status": "ACTIVE"}}'

agent = Agent(
    name="TelemetryAgent",
    instructions="""You are a predictive maintenance analyst.

You receive: machine_id, vibration_mm_s, temperature_C, rpm, pressure_bar

Decision rules, in order:
1. Vibration > 8.0 mm/s -> FAILURE_ALERT
2. Temperature > 90.0 °C -> OVERHEAT_ALERT
3. RPM < 1400 or RPM > 1600 -> ANOMALY_ALERT: rpm_out_of_range
4. Pressure < 2.0 or Pressure > 3.5 bar -> ANOMALY_ALERT: pressure_out_of_range
5. Else -> NORMAL

Tool policy:
- Call get_telemetry_logs(machine_id) once if you were not given live values
- Do not call it repeatedly

Output, exactly one line:
DECISION: <FAILURE_ALERT|OVERHEAT_ALERT|ANOMALY_ALERT|NORMAL>
REASON: <vibration=X, temp=Y, rpm=Z>
VALUES: temp_C=<n>, vibration_mm_s=<n>, rpm=<n>, pressure_bar=<n>
""",
    client=OpenAIChatCompletionClient(
        model="Qwen/Qwen2.5-VL-7B-Instruct",
        api_key="EMPTY",
        base_url="http://localhost:8000/v1",
    ),
    tools=[get_telemetry_logs]
)