import uuid
from typing import Any
from pydantic import BaseModel
from app.db.models import Ticket
from app.plugins.base import BasePlugin
from app.plugins.registry import registry


class TicketParams(BaseModel):
    priority: str = "HIGH"
    provider: str = "jira"
    critical_only: bool = False
    deduplicate: bool = True


@registry.register
class JiraTicketingPlugin(BasePlugin):
    name = "jira_ticketing"
    category = "ticketing"
    description = "Creates prioritized incident tickets in SQL with deduplication and external reference tracking."
    input_schema = TicketParams

    def execute(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        cfg = self.validate_params(params)
        db = context["db"]
        exec_id = context.get("execution_id")
        alerts = context.get("critical_alerts", []) if cfg.critical_only else context.get("alerts", [])

        created, skipped = [], []
        for a in alerts:
            uid = str(a.get("uid") or a.get("device/link") or uuid.uuid4())
            device = str(a.get("device/link") or a.get("hostname") or "Unknown")
            ip = str(a.get("ip_address") or "")
            intensity = str(a.get("intensity") or "HIGH").upper()
            mins = a.get("active_since", 0)
            ext_ref = str(a.get("ticket_id") or "").strip()

            if cfg.deduplicate:
                existing = db.query(Ticket).filter(Ticket.alert_uid == uid, Ticket.status == "OPEN").first()
                if existing:
                    skipped.append({"ticket_key": existing.ticket_key, "device": existing.device, "alert_uid": uid})
                    continue

            key = f"{cfg.provider.upper()}-{db.query(Ticket).count() + 1001}"
            summary = f"[{intensity}] {device} ({a.get('metric', 'LINK')}) - Active {mins}m"
            desc_lines = [
                f"Device: {device}",
                f"IP: {ip or 'N/A'}",
                f"Client: {a.get('client', 'N/A')}",
                f"Intensity: {intensity}",
                f"Active Since: {mins} minutes",
                f"External Reference: {ext_ref or 'None'}",
            ]
            desc = "\n".join(desc_lines)

            ticket_row = Ticket(
                ticket_key=key,
                execution_id=exec_id,
                alert_uid=uid,
                device=device,
                ip_address=ip,
                priority=cfg.priority.upper(),
                provider=cfg.provider.lower(),
                summary=summary,
                description=desc,
                status="OPEN",
            )
            db.add(ticket_row)
            db.commit()
            created.append(
                {
                    "ticket_key": key,
                    "device": device,
                    "ip_address": ip,
                    "priority": cfg.priority.upper(),
                    "active_since_min": mins,
                    "external_ref": ext_ref or None,
                }
            )

        context["created_tickets"] = created
        context["tickets_created_count"] = len(created)
        return {"created": len(created), "skipped_duplicates": len(skipped), "tickets": created}
