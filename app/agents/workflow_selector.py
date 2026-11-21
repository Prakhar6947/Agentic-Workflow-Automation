import json
import uuid
from app.db.database import SessionLocal
from app.db.models import Workflow
from app.agents.llm import get_deterministic_plan, get_llm_plan
from app.agents.state import AutomationState
from app.plugins.registry import registry


def workflow_selection_agent(state: AutomationState) -> AutomationState:
    db = SessionLocal()
    try:
        # If forced workflow code is passed (manual run or scheduled trigger)
        if state.get("forced_workflow_code"):
            wf = db.query(Workflow).filter(Workflow.code == state["forced_workflow_code"]).first()
            if not wf:
                return {
                    **state,
                    "validation_errors": [f"Workflow '{state['forced_workflow_code']}' not found."],
                    "status": "failed",
                }
            steps = json.loads(wf.definition_json).get("steps", [])
            forced = state.get("forced_params") or {}
            for s in steps:
                plugin = registry.get(s["plugin"])
                if plugin:
                    valid_keys = set(plugin.input_schema.model_fields.keys())
                    s["params"] = {**s.get("params", {}), **{k: v for k, v in forced.items() if k in valid_keys}}
            return {
                **state,
                "selected_mode": wf.workflow_type,
                "workflow_id": wf.id,
                "workflow_code": wf.code,
                "workflow_name": wf.name,
                "workflow_steps": steps,
                "extracted_params": forced,
                "is_scheduled": False,
                "validation_errors": [],
            }

        # Query catalog of existing workflows
        catalog = [{"code": w.code, "name": w.name, "description": w.description} for w in db.query(Workflow).all()]
        user_prompt = state.get("user_prompt", "")

        # Try LLM first; if unavailable or failed, fallback to deterministic parser
        plan = get_llm_plan(user_prompt, catalog) or get_deterministic_plan(user_prompt)

        if plan["mode"] == "predefined":
            wf_row = db.query(Workflow).filter(Workflow.code == plan["workflow_code"]).first()
            wf_id = wf_row.id if wf_row else None
            wf_name = wf_row.name if wf_row else plan["workflow_name"]
        else:
            # Dynamic workflow: persist to SQL workflows table
            code = plan["workflow_code"]
            if db.query(Workflow).filter(Workflow.code == code).first():
                code = f"WF_DYN_{uuid.uuid4().hex[:6].upper()}"
                plan["workflow_code"] = code

            wf_row = Workflow(
                code=code,
                name=plan["workflow_name"],
                description=plan.get("workflow_description", "Dynamically composed DAG"),
                workflow_type="dynamic",
                definition_json=json.dumps({"steps": plan["steps"]}),
            )
            db.add(wf_row)
            db.commit()
            db.refresh(wf_row)
            wf_id = wf_row.id
            wf_name = wf_row.name

        return {
            **state,
            "selected_mode": plan["mode"],
            "workflow_id": wf_id,
            "workflow_code": plan["workflow_code"],
            "workflow_name": wf_name,
            "workflow_steps": plan["steps"],
            "extracted_params": plan.get("extracted_params", {}),
            "is_scheduled": bool(plan.get("is_scheduled")),
            "schedule_spec": plan.get("schedule"),
            "validation_errors": [],
        }
    finally:
        db.close()
