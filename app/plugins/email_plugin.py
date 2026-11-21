import smtplib
from email.message import EmailMessage
from typing import Any
from pydantic import BaseModel
from app.config import DEFAULT_OPS_EMAIL, SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER
from app.db.models import EmailLog
from app.plugins.base import BasePlugin
from app.plugins.registry import registry


class EmailParams(BaseModel):
    recipient: str = ""
    subject: str = "Automated Operations Report"
    body_override: str | None = None


@registry.register
class EmailNotifierPlugin(BasePlugin):
    name = "email_notifier"
    category = "notification"
    description = "Sends workflow reports via SMTP if configured and logs delivery to SQL email_logs."
    input_schema = EmailParams

    def execute(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        cfg = self.validate_params(params)
        recipient = cfg.recipient.strip() if cfg.recipient and cfg.recipient.strip() else DEFAULT_OPS_EMAIL

        if cfg.body_override:
            body = cfg.body_override
        else:
            parts = [p for p in [context.get("alert_summary"), context.get("performance_report")] if p]
            if context.get("created_tickets"):
                t_lines = ["### Created Tickets"] + [
                    f"- {t['ticket_key']} | {t['priority']} | {t['device']}" for t in context["created_tickets"]
                ]
                parts.append("\n".join(t_lines))
            body = "\n\n---\n\n".join(parts) or "Workflow executed with no output items."

        status = "SENT_LOGGED"
        if SMTP_HOST and SMTP_USER and SMTP_PASSWORD:
            try:
                msg = EmailMessage()
                msg["From"] = SMTP_FROM
                msg["To"] = recipient
                msg["Subject"] = cfg.subject
                msg.set_content(body)
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as srv:
                    srv.starttls()
                    srv.login(SMTP_USER, SMTP_PASSWORD)
                    srv.send_message(msg)
                status = "SENT_SMTP"
            except Exception as exc:
                status = f"SMTP_FALLBACK ({exc.__class__.__name__})"

        db = context["db"]
        exec_id = context.get("execution_id")
        row = EmailLog(
            execution_id=exec_id,
            recipient=recipient,
            subject=cfg.subject,
            body=body,
            status=status,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        res = {"email_log_id": row.id, "recipient": recipient, "subject": cfg.subject, "status": status}
        context["email_sent"] = res
        return res
