from agent_framework import WorkflowBuilder
from agents.defect_analysis_agent import defect_analysis_agent
from agents.telemetry_agent import telemetry_agent
from agents.safety_agent import safety_agent
from agents.orchestrator_agent import orchestrator_agent
from workflows.decision_router import decision_router, action_executor_node

builder = WorkflowBuilder("FactoryMonitor")

n_vision = builder.add_agent_node("defect_analysis", defect_analysis_agent)
n_telemetry = builder.add_agent_node("telemetry", telemetry_agent)
n_safety = builder.add_agent_node("safety", safety_agent)

n_decide = builder.add_condition_node(
    "decision_router",
    decision_router,
    routes=["critical_maintenance", "safety_violation", "quality_defect", "normal"]
)

n_action = builder.add_function_node(
    "action_executor",
    lambda state: action_executor_node(state, orchestrator_agent)
)

builder.set_entry_point([n_vision, n_telemetry, n_safety])
builder.add_edge([n_vision, n_telemetry, n_safety], n_decide)
builder.add_edge(n_decide, n_action)

factory_workflow = builder.build()