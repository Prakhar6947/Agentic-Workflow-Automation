from app.db.database import SessionLocal
from app.db.models import WorkflowExecution
from app.agents.state import AutomationState


def reporting_agent(state: AutomationState) -> AutomationState:
    if state.get("validation_errors"):
        report = "### Workflow Validation Errors:\n" + "\n".join(f"- {e}" for e in state["validation_errors"])
        return {**state, "status": "failed", "final_report": report}

    wf_name = state.get("workflow_name", "Automation Workflow")
    wf_code = state.get("workflow_code", "UNKNOWN")
    mode = state.get("selected_mode", "predefined")
    status = state.get("status", "completed")
    exec_id = state.get("execution_id")

    lines = [
        f"## {wf_name} (`{wf_code}`)",
        f"- **Mode:** `{mode}` | **Status:** `{status.upper()}`" + (f" | **Execution ID:** `#{exec_id}`" if exec_id else ""),
    ]

    if state.get("registered_schedule"):
        s = state["registered_schedule"]
        lines.append(
            f"- **Schedule Registered:** Schedule ID `#{s['id']}` (`{s['cron_expression']}` | Next Run: `{s.get('next_run_at', 'Pending')}`)"
        )

    ctx = state.get("shared_context") or {}
    if ctx.get("alert_summary"):
        lines.append("\n" + ctx["alert_summary"])

    if ctx.get("performance_report"):
        lines.append("\n" + ctx["performance_report"])

    if ctx.get("created_tickets"):
        lines.append("\n### Created Tickets")
        for t in ctx["created_tickets"]:
            ref_info = f" (Ref: `{t['external_ref']}`)" if t.get("external_ref") else ""
            lines.append(f"- **{t['ticket_key']}** | `{t['priority']}` | `{t['device']}` ({t.get('ip_address', 'N/A')}){ref_info}")

    if ctx.get("email_sent"):
        e = ctx["email_sent"]
        lines.append(
            f"\n### Email Notification\n- **Recipient:** `{e['recipient']}`\n- **Subject:** {e['subject']}\n- **Delivery Status:** `{e['status']}`"
        )

    # Note skipped steps if any
    skipped = [s for s in state.get("step_results", []) if s.get("status") == "skipped"]
    if skipped:
        lines.append("\n### Condition Audit (Skipped Steps)")
        for sk in skipped:
            lines.append(f"- Step `{sk['step']}` skipped: condition `{sk['condition']}` evaluated to False.")

    report = "\n".join(lines)

    if exec_id:
        db = SessionLocal()
        try:
            row = db.query(WorkflowExecution).filter(WorkflowExecution.id == exec_id).first()
            if row:
                row.final_report = report
                db.commit()
        finally:
            db.close()

    return {**state, "final_report": report}
