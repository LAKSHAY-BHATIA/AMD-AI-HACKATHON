from agent_framework.orchestrations import SequentialBuilder
# FIX: Use relative sibling imports instead of an absolute 'agents.' path
from telemetry_agent import agent as telemetry_agent
from defect_analysis_agent import agent as defect_agent

# Chain both agents into an assembly line execution team
workflow = SequentialBuilder(participants=[telemetry_agent, defect_agent]).build()


agent = workflow

# Wrap the pipeline workflow as a single executable Agent instance for DevUI
#agent = workflow.as_agent(name="ManufacturingPipeline")