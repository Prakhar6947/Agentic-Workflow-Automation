from typing import Any
from pydantic import BaseModel
from app.plugins.base import BasePlugin
from app.plugins.registry import registry


class AlertSummaryParams(BaseModel):
    title: str = "Operational Alert Summary"


@registry.register
class AlertSummarizerPlugin(BasePlugin):
    name = "alert_summarizer"
    category = "analytics"
    description = "Synthesizes a structured markdown summary of collected operational alerts."
    input_schema = AlertSummaryParams

    def execute(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        cfg = self.validate_params(params)
        alerts = context.get("alerts", [])
        counts: dict[str, int] = {}
        for a in alerts:
            k = str(a.get("intensity") or "UNKNOWN").upper()
            counts[k] = counts.get(k, 0) + 1

        lines = [
            f"### {cfg.title}",
            f"- **Matching Alerts:** {len(alerts)}",
            f"- **Severity Breakdown:** {', '.join(f'{k}: {v}' for k, v in counts.items()) or 'None'}",
        ]
        for a in alerts:
            dev = a.get("device/link") or a.get("hostname") or "Unknown"
            ip = a.get("ip_address") or "N/A"
            metric = a.get("metric") or "Telemetry Alert"
            active_min = a.get("active_since", 0)
            lines.append(
                f"- `{dev}` ({ip}) | **{a.get('intensity')}** | {metric} | Active {active_min}m"
            )

        summary = "\n".join(lines)
        context["alert_summary"] = summary
        return {"alert_count": len(alerts), "by_intensity": counts, "summary_markdown": summary}
