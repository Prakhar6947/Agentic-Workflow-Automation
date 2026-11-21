import json
import time
from datetime import datetime, timezone
from app.db.database import SessionLocal
from app.db.models import ExecutionStepLog, WorkflowExecution
from app.agents.condition_eval import evaluate_condition
from app.agents.state import AutomationState
from app.plugins.registry import registry


def execution_agent(state: AutomationState) -> AutomationState:
    db = SessionLocal()
    try:
        exec_row = WorkflowExecution(
            workflow_id=state.get("workflow_id"),
            schedule_id=state.get("schedule_id"),
            trigger_type=state.get("trigger_type", "chat"),
            user_prompt=state.get("user_prompt", ""),
            extracted_params_json=json.dumps(state.get("extracted_params", {})),
            selected_plugins_json=json.dumps(state.get("selected_plugins", [])),
            status="running",
        )
        db.add(exec_row)
        db.commit()
        db.refresh(exec_row)

        ctx = {"db": db, "execution_id": exec_row.id}
        results, final_status, err_msg = [], "completed", None

        for idx, step in enumerate(state.get("workflow_steps", [])):
            t0 = time.perf_counter()
            cond = step.get("condition", "always")
            try:
                cond_met = evaluate_condition(cond, ctx)
            except Exception as cond_err:
                cond_met = False
                err_msg = str(cond_err)

            if not cond_met:
                out = {"skipped": True, "condition": cond, "reason": "Condition expression evaluated to False"}
                step_status = "skipped"
            else:
                plugin = registry.get(step["plugin"])
                if not plugin:
                    out = {"error": f"Plugin '{step['plugin']}' not found in registry"}
                    step_status, final_status, err_msg = "failed", "failed", out["error"]
                else:
                    try:
                        out = plugin.execute(step.get("params", {}), ctx)
                        step_status = "completed"
                    except Exception as exc:
                        out = {"error": str(exc), "error_type": exc.__class__.__name__}
                        step_status, final_status, err_msg = "failed", "failed", str(exc)

            ms = int((time.perf_counter() - t0) * 1000)
            step_log = ExecutionStepLog(
                execution_id=exec_row.id,
                step_index=idx,
                step_name=step.get("name", f"step_{idx}"),
                plugin_name=step.get("plugin", "unknown"),
                condition_expr=cond,
                condition_met=cond_met,
                status=step_status,
                input_json=json.dumps(step.get("params", {})),
                output_json=json.dumps(out, default=str),
                duration_ms=ms,
            )
            db.add(step_log)
            db.commit()

            results.append(
                {
                    "step": step.get("name"),
                    "plugin": step.get("plugin"),
                    "condition": cond,
                    "condition_met": cond_met,
                    "status": step_status,
                    "duration_ms": ms,
                    "output": out,
                }
            )
            if step_status == "failed":
                break

        exec_row.status = final_status
        exec_row.error_message = err_msg
        exec_row.completed_at = datetime.now(timezone.utc)
        db.commit()

        # Remove non-serializable objects from context for state return
        safe_ctx = {k: v for k, v in ctx.items() if k != "db"}
        return {
            **state,
            "execution_id": exec_row.id,
            "step_results": results,
            "shared_context": safe_ctx,
            "status": final_status,
        }
    finally:
        db.close()
