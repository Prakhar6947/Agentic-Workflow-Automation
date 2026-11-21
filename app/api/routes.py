import json
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.agents.graph import automation_graph
from app.api.schemas import ChatRequest, ManualRunRequest, ScheduleCreateRequest
from app.db.database import get_db
from app.db.models import ChatMessage, EmailLog, Schedule, Ticket, Workflow, WorkflowExecution
from app.plugins.registry import registry
from app.scheduler.service import scheduler_service

router = APIRouter()


@router.post("/chat")
def chat_endpoint(req: ChatRequest, db: Session = Depends(get_db)):
    # Record incoming chat message
    db.add(ChatMessage(role="user", content=req.prompt))
    db.commit()

    res = automation_graph.invoke(
        {
            "user_prompt": req.prompt,
            "trigger_type": "chat",
            "execute_now": req.execute_now,
        }
    )

    # Record assistant chat message
    report = res.get("final_report", "")
    exec_id = res.get("execution_id")
    db.add(ChatMessage(role="assistant", content=report, execution_id=exec_id))
    db.commit()

    return {
        "status": res.get("status"),
        "mode": res.get("selected_mode"),
        "workflow_code": res.get("workflow_code"),
        "execution_id": res.get("execution_id"),
        "schedule": res.get("registered_schedule"),
        "extracted_params": res.get("extracted_params"),
        "selected_plugins": res.get("selected_plugins"),
        "step_results": res.get("step_results"),
        "report": report,
    }


@router.get("/workflows")
def list_workflows(db: Session = Depends(get_db)):
    return [
        {
            "id": w.id,
            "code": w.code,
            "name": w.name,
            "description": w.description,
            "type": w.workflow_type,
            "is_active": w.is_active,
            "definition": json.loads(w.definition_json),
            "created_at": w.created_at.isoformat() if w.created_at else None,
        }
        for w in db.query(Workflow).all()
    ]


@router.post("/workflows/{code}/execute")
def run_workflow_manually(code: str, req: ManualRunRequest):
    res = automation_graph.invoke(
        {
            "user_prompt": f"Manual run of workflow {code}",
            "trigger_type": "manual",
            "execute_now": True,
            "forced_workflow_code": code,
            "forced_params": req.params,
        }
    )
    if res.get("validation_errors"):
        raise HTTPException(status_code=400, detail=res["validation_errors"])
    return {
        "execution_id": res.get("execution_id"),
        "workflow_code": code,
        "status": res.get("status"),
        "step_results": res.get("step_results"),
        "report": res.get("final_report"),
    }


@router.get("/schedules")
def list_schedules(db: Session = Depends(get_db)):
    return [
        {
            "id": s.id,
            "workflow_id": s.workflow_id,
            "workflow_code": s.workflow.code if s.workflow else None,
            "name": s.name,
            "schedule_type": s.schedule_type,
            "cron": s.cron_expression,
            "is_active": s.is_active,
            "parameters": json.loads(s.parameters_json or "{}"),
            "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
            "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in db.query(Schedule).all()
    ]


@router.post("/schedules")
def create_schedule(req: ScheduleCreateRequest, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.code == req.workflow_code).first()
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{req.workflow_code}' not found")
    return scheduler_service.register(
        workflow_id=wf.id,
        name=req.name,
        schedule_type=req.schedule_type,
        cron_expression=req.cron_expression,
        parameters=req.parameters,
        prompt_origin="API schedule creation",
    )


@router.post("/schedules/{schedule_id}/trigger")
def trigger_schedule(schedule_id: int):
    res = scheduler_service.run_schedule(schedule_id)
    if not res:
        raise HTTPException(status_code=404, detail=f"Schedule #{schedule_id} not found or inactive")
    return {
        "execution_id": res.get("execution_id"),
        "status": res.get("status"),
        "report": res.get("final_report"),
        "step_results": res.get("step_results"),
    }


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int):
    scheduler_service.remove(schedule_id)
    return {"message": f"Schedule #{schedule_id} deleted or deactivated"}


@router.get("/executions")
def list_executions(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(WorkflowExecution).order_by(WorkflowExecution.id.desc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "workflow_id": e.workflow_id,
            "workflow_code": e.workflow.code if e.workflow else "DYNAMIC",
            "schedule_id": e.schedule_id,
            "trigger": e.trigger_type,
            "status": e.status,
            "prompt": e.user_prompt,
            "started_at": e.started_at.isoformat() if e.started_at else None,
            "completed_at": e.completed_at.isoformat() if e.completed_at else None,
            "steps": [
                {
                    "step": l.step_name,
                    "plugin": l.plugin_name,
                    "condition": l.condition_expr,
                    "condition_met": l.condition_met,
                    "status": l.status,
                    "ms": l.duration_ms,
                }
                for l in e.step_logs
            ],
            "report": e.final_report,
        }
        for e in rows
    ]


@router.get("/executions/{execution_id}")
def get_execution_detail(execution_id: int, db: Session = Depends(get_db)):
    e = db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
    if not e:
        raise HTTPException(status_code=404, detail=f"Execution #{execution_id} not found")
    return {
        "id": e.id,
        "workflow_id": e.workflow_id,
        "workflow_code": e.workflow.code if e.workflow else "DYNAMIC",
        "schedule_id": e.schedule_id,
        "trigger": e.trigger_type,
        "status": e.status,
        "prompt": e.user_prompt,
        "extracted_params": json.loads(e.extracted_params_json or "{}"),
        "selected_plugins": json.loads(e.selected_plugins_json or "[]"),
        "report": e.final_report,
        "error_message": e.error_message,
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        "step_logs": [
            {
                "index": l.step_index,
                "step": l.step_name,
                "plugin": l.plugin_name,
                "condition": l.condition_expr,
                "condition_met": l.condition_met,
                "status": l.status,
                "input": json.loads(l.input_json or "{}"),
                "output": json.loads(l.output_json or "{}"),
                "duration_ms": l.duration_ms,
            }
            for l in e.step_logs
        ],
        "tickets": [
            {"key": t.ticket_key, "device": t.device, "priority": t.priority, "status": t.status}
            for t in e.tickets
        ],
        "emails": [
            {"id": em.id, "to": em.recipient, "subject": em.subject, "status": em.status}
            for em in e.emails
        ],
    }


@router.get("/tickets")
def list_tickets(db: Session = Depends(get_db)):
    return [
        {
            "id": t.id,
            "key": t.ticket_key,
            "execution_id": t.execution_id,
            "alert_uid": t.alert_uid,
            "device": t.device,
            "ip_address": t.ip_address,
            "priority": t.priority,
            "provider": t.provider,
            "summary": t.summary,
            "status": t.status,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in db.query(Ticket).order_by(Ticket.id.desc()).all()
    ]


@router.get("/emails")
def list_emails(db: Session = Depends(get_db)):
    return [
        {
            "id": e.id,
            "execution_id": e.execution_id,
            "to": e.recipient,
            "subject": e.subject,
            "body": e.body,
            "status": e.status,
            "sent_at": e.sent_at.isoformat() if e.sent_at else None,
        }
        for e in db.query(EmailLog).order_by(EmailLog.id.desc()).all()
    ]


@router.get("/plugins")
def list_plugins():
    return registry.list_plugins()
