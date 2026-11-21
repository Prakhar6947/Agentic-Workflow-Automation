from langgraph.graph import END, START, StateGraph
from app.agents.executor import execution_agent
from app.agents.plugin_selector import plugin_selection_agent
from app.agents.reporter import reporting_agent
from app.agents.state import AutomationState
from app.agents.workflow_selector import workflow_selection_agent
from app.scheduler.service import scheduler_service


def schedule_registration_node(state: AutomationState) -> AutomationState:
    spec = state.get("schedule_spec")
    if not spec:
        return state

    reg = scheduler_service.register(
        workflow_id=state["workflow_id"],
        name=f"Scheduled: {state['workflow_name']}",
        schedule_type=spec["schedule_type"],
        cron_expression=spec["cron_expression"],
        parameters=state.get("extracted_params", {}),
        prompt_origin=state.get("user_prompt", ""),
    )
    return {**state, "schedule_id": reg["id"], "registered_schedule": reg}


def build_automation_graph():
    g = StateGraph(AutomationState)

    g.add_node("workflow_selection", workflow_selection_agent)
    g.add_node("plugin_selection", plugin_selection_agent)
    g.add_node("schedule_registration", schedule_registration_node)
    g.add_node("execution", execution_agent)
    g.add_node("reporting", reporting_agent)

    g.add_edge(START, "workflow_selection")

    g.add_conditional_edges(
        "workflow_selection",
        lambda s: "reporting" if s.get("validation_errors") else "plugin_selection",
        {"plugin_selection": "plugin_selection", "reporting": "reporting"},
    )

    g.add_conditional_edges(
        "plugin_selection",
        lambda s: "reporting"
        if s.get("validation_errors")
        else ("schedule_registration" if s.get("is_scheduled") and s.get("schedule_spec") else "execution"),
        {
            "schedule_registration": "schedule_registration",
            "execution": "execution",
            "reporting": "reporting",
        },
    )

    g.add_conditional_edges(
        "schedule_registration",
        lambda s: "execution" if s.get("execute_now", True) else "reporting",
        {"execution": "execution", "reporting": "reporting"},
    )

    g.add_edge("execution", "reporting")
    g.add_edge("reporting", END)

    return g.compile()


automation_graph = build_automation_graph()
