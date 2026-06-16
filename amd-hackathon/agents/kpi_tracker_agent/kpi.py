from agent_framework import Agent
from config import create_client
from tools.kpi_tools import log_kpi_live

#kpi_tracker_agent

agent = Agent(
    name="KPI_TrackerAgent",
    instructions="Log factory KPIs via log_kpi_live. Always log.",
    client=create_client(),
    tools=[log_kpi_live])

kpi_tracker_agent = agent