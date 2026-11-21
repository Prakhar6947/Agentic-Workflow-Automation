from pydantic import ValidationError
from app.agents.state import AutomationState
from app.plugins.registry import registry


def plugin_selection_agent(state: AutomationState) -> AutomationState:
    errors = list(state.get("validation_errors", []))
    selected = []
    steps = state.get("workflow_steps", [])

    for idx, step in enumerate(steps):
        plugin_name = step.get("plugin", "")
        plugin = registry.get(plugin_name)
        if not plugin:
            errors.append(f"Step {idx + 1} ('{step.get('name')}'): unknown plugin '{plugin_name}'.")
            continue

        raw_params = step.get("params") or {}
        try:
            validated = plugin.validate_params(raw_params)
            step["params"] = validated.model_dump()
        except ValidationError as exc:
            errors.append(f"Step {idx + 1} ('{step.get('name')}', {plugin_name}): {exc}")
            continue

        selected.append(
            {
                "step": step.get("name"),
                "plugin": plugin.name,
                "category": plugin.category,
                "condition": step.get("condition", "always"),
            }
        )

    return {
        **state,
        "workflow_steps": steps,
        "selected_plugins": selected,
        "validation_errors": errors,
    }
