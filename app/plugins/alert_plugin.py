import json
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
from app.config import ALERTS_PATH
from app.plugins.base import BasePlugin
from app.plugins.registry import registry


class AlertSourceParams(BaseModel):
    intensities: list[str] = Field(default_factory=list)
    unresolved_only: bool = False
    min_active_minutes: int = Field(default=0, ge=0)
    client: str | None = None
    bucket: str | None = None


@registry.register
class AlertSourcePlugin(BasePlugin):
    name = "alert_source"
    category = "data_source"
    description = "Loads and filters alerts from alerts telemetry (alerts.json)."
    input_schema = AlertSourceParams

    def execute(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        cfg = self.validate_params(params)
        path = ALERTS_PATH if ALERTS_PATH.exists() else Path("alerts.json")
        if not path.exists():
            path = Path("data/alerts.json")

        all_alerts = json.loads(path.read_text(encoding="utf-8")).get("data", [])
        wanted = {i.upper() for i in cfg.intensities if i}
        matched = []

        for a in all_alerts:
            intensity = str(a.get("intensity") or "").upper()
            if wanted and intensity not in wanted:
                continue
            if cfg.unresolved_only and (a.get("acknowledged") or str(a.get("ticket_id") or "").strip()):
                continue
            if cfg.min_active_minutes > 0 and int(a.get("active_since") or 0) <= cfg.min_active_minutes:
                continue
            if cfg.client and cfg.client.lower() not in str(a.get("client") or "").lower():
                continue
            if cfg.bucket and cfg.bucket.lower() != str(a.get("bucket") or "").lower():
                continue
            matched.append(a)

        critical = [a for a in matched if str(a.get("intensity") or "").upper() == "DOWN"]
        context["alerts"] = matched
        context["critical_alerts"] = critical
        context["alert_count"] = len(matched)
        context["critical_count"] = len(critical)

        return {
            "total_source": len(all_alerts),
            "matched_count": len(matched),
            "critical_count": len(critical),
            "alerts": matched,
        }
