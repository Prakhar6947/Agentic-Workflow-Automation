import json
from datetime import datetime, timezone
from typing import Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.db.database import SessionLocal
from app.db.models import Schedule, Workflow


class SchedulerService:
    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler(timezone="UTC")
        self._started = False

    def start(self) -> None:
        if not self._started:
            self.scheduler.start()
            self._started = True
        db = SessionLocal()
        try:
            for sched in db.query(Schedule).filter(Schedule.is_active.is_(True)).all():
                try:
                    self._bind_job(sched, db)
                except Exception as exc:
                    print(f"Warning: Failed to bind schedule #{sched.id}: {exc}")
        finally:
            db.close()

    def shutdown(self) -> None:
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False

    def _bind_job(self, sched: Schedule, db) -> datetime | None:
        job_id = f"sched_{sched.id}"
        job = self.scheduler.add_job(
            self.run_schedule,
            trigger=CronTrigger.from_crontab(sched.cron_expression),
            id=job_id,
            args=[sched.id],
            replace_existing=True,
        )
        next_run = getattr(job, "next_run_time", None)
        sched.next_run_at = next_run
        db.commit()
        return next_run

    def register(
        self,
        workflow_id: int,
        name: str,
        schedule_type: str,
        cron_expression: str,
        parameters: dict[str, Any],
        prompt_origin: str = "",
    ) -> dict[str, Any]:
        db = SessionLocal()
        try:
            sched = Schedule(
                workflow_id=workflow_id,
                name=name,
                schedule_type=schedule_type,
                cron_expression=cron_expression,
                parameters_json=json.dumps(parameters or {}),
                prompt_origin=prompt_origin,
            )
            db.add(sched)
            db.commit()
            db.refresh(sched)
            next_run = self._bind_job(sched, db)
            return {
                "id": sched.id,
                "workflow_id": workflow_id,
                "name": sched.name,
                "schedule_type": schedule_type,
                "cron_expression": cron_expression,
                "next_run_at": next_run.isoformat() if next_run else None,
            }
        finally:
            db.close()

    def remove(self, schedule_id: int) -> None:
        job_id = f"sched_{schedule_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        db = SessionLocal()
        try:
            sched = db.query(Schedule).filter(Schedule.id == schedule_id).first()
            if sched:
                sched.is_active = False
                db.commit()
        finally:
            db.close()

    def run_schedule(self, schedule_id: int) -> dict[str, Any] | None:
        from app.agents.graph import automation_graph

        db = SessionLocal()
        try:
            sched = db.query(Schedule).filter(Schedule.id == schedule_id, Schedule.is_active.is_(True)).first()
            if not sched:
                return None
            wf = db.query(Workflow).filter(Workflow.id == sched.workflow_id).first()
            if not wf:
                return None
            sched.last_run_at = datetime.now(timezone.utc)
            db.commit()
            wf_code = wf.code
            params = json.loads(sched.parameters_json or "{}")
            prompt = sched.prompt_origin
        finally:
            db.close()

        return automation_graph.invoke(
            {
                "user_prompt": prompt or f"Scheduled run of {wf_code}",
                "trigger_type": "schedule",
                "execute_now": True,
                "forced_workflow_code": wf_code,
                "forced_params": params,
                "schedule_id": schedule_id,
            }
        )


scheduler_service = SchedulerService()
