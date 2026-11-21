import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
from app.config import PERF_PATH
from app.plugins.base import BasePlugin
from app.plugins.registry import registry


class PerformanceParams(BaseModel):
    location: str | None = None
    hours: int = Field(default=6, ge=1, le=720)


@registry.register
class PerformanceSourcePlugin(BasePlugin):
    name = "performance_source"
    category = "data_source"
    description = "Loads network link performance metrics from performance telemetry (performance_stats.json)."
    input_schema = PerformanceParams

    def execute(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        cfg = self.validate_params(params)
        path = PERF_PATH if PERF_PATH.exists() else Path("performance_stats.json")
        if not path.exists():
            path = Path("data/performance_stats.json")

        raw = json.loads(path.read_text(encoding="utf-8"))
        rows = raw.get("data", {}).get("performance_stats_table", {}).get("ip_table_info", {}).get("data", [])
        zones = sorted({str(r.get("site_zone") or "Unknown") for r in rows})

        if cfg.location:
            q = cfg.location.strip().lower()
            matched = [
                r for r in rows
                if q in str(r.get("site_zone") or "").lower()
                or q in str(r.get("site_address") or "").lower()
                or q in str(r.get("site_code") or "").lower()
            ]
        else:
            matched = rows

        end_str = raw.get("date", {}).get("end", "")
        window = f"Last {cfg.hours} hours"
        if end_str:
            try:
                end_dt = datetime.fromisoformat(end_str)
                window = f"{(end_dt - timedelta(hours=cfg.hours)).isoformat()} to {end_dt.isoformat()}"
            except Exception:
                pass

        def compute(items: list[dict[str, Any]]) -> dict[str, Any]:
            if not items:
                return {"total_links": 0, "down_links": 0, "avg_uptime": 0.0, "avg_score": 0.0, "avg_latency": 0.0}
            n = len(items)
            down = sum(1 for r in items if float(r.get("uptime", 0)) == 0.0)
            up = [r for r in items if float(r.get("uptime", 0)) > 0.0]
            return {
                "total_links": n,
                "down_links": down,
                "avg_uptime": round(sum(float(r.get("uptime", 0)) for r in items) / n, 2),
                "avg_score": round(sum(float(r.get("performance_score", 0)) for r in items) / n, 2),
                "avg_latency": round(sum(float(r.get("avg_latency", 0)) for r in up) / len(up), 2) if up else 0.0,
            }

        metrics = compute(matched)
        region = cfg.location or "All Zones"
        lines = [f"### Performance Report - {region}", f"- **Window:** {window}"]

        if matched:
            lines.extend(
                [
                    f"- **Links Analyzed:** {metrics['total_links']} (Down: {metrics['down_links']})",
                    f"- **Avg Uptime:** {metrics['avg_uptime']}%",
                    f"- **Avg Performance Score:** {metrics['avg_score']}/100",
                    f"- **Avg Latency (Active Links):** {metrics['avg_latency']} ms",
                ]
            )
        else:
            baseline = compute(rows)
            lines.extend(
                [
                    f"- **Matching Links for `{cfg.location}`:** 0",
                    f"- **Available Zones in Dataset:** {', '.join(zones)}",
                    f"- **Dataset Baseline ({baseline['total_links']} links):** Avg Uptime {baseline['avg_uptime']}%, Down Links: {baseline['down_links']}",
                ]
            )

        report_md = "\n".join(lines)
        context["performance_report"] = report_md
        context["down_links"] = metrics["down_links"]
        return {"location": cfg.location, "window": window, "metrics": metrics, "available_zones": zones}
