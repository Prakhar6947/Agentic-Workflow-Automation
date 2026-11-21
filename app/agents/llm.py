import json
import re
import uuid
from typing import Any
from app.config import (
    DEFAULT_OPS_EMAIL,
    GEMINI_MODEL,
    GOOGLE_API_KEY,
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)
from app.agents.state import WorkflowPlan
from app.plugins.registry import registry


def parse_schedule_expression(text: str) -> dict[str, str] | None:
    lower = text.lower()
    hour, minute = 9, 0
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", lower)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if m.group(3) == "pm" and hour != 12:
            hour += 12
        elif m.group(3) == "am" and hour == 12:
            hour = 0

    if any(k in lower for k in ["every day", "daily"]):
        return {"schedule_type": "daily", "cron_expression": f"{minute} {hour} * * *"}
    if any(k in lower for k in ["every week", "weekly"]):
        return {"schedule_type": "weekly", "cron_expression": f"{minute} {hour} * * mon"}
    if any(k in lower for k in ["every month", "monthly"]):
        return {"schedule_type": "monthly", "cron_expression": f"{minute} {hour} 1 * *"}
    return None


def get_llm_plan(prompt: str, catalog: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Attempts LLM planning with Gemini or OpenAI. Returns structured plan dict or None on failure.
    """
    sys_prompt = (
        "You are an AI Workflow Selection Agent in an Agentic Automation Engine.\n"
        "Your task is to analyze the user request and determine whether to route to a predefined workflow (WF001..WF004) "
        "or compose a dynamic multi-step DAG (WF_DYN_...).\n\n"
        f"Available Predefined Catalog: {json.dumps(catalog, indent=2)}\n"
        f"Available Plugins: {json.dumps([p['name'] for p in registry.list_plugins()])}\n"
        f"Default Operations Email: {DEFAULT_OPS_EMAIL}\n"
        f"User Prompt: {prompt}\n\n"
        "Instructions:\n"
        "1. If the request matches a predefined workflow (e.g. single action like ticket creation or alert summary alone), "
        "set mode='predefined' and workflow_code to WF001/WF002/WF003/WF004 with appropriate parameters.\n"
        "2. If the request spans multiple stages (e.g., alert collection + summarization + conditional ticketing + email), "
        "set mode='dynamic', generate a new code 'WF_DYN_<HASH>', and list the ordered steps with safe AST conditions.\n"
        "3. Detect any schedule triggers (e.g. 'Every day at 9 AM' -> daily, '0 9 * * *').\n"
        "4. Validate parameters strictly against plugin capabilities."
    )

    if GOOGLE_API_KEY and LLM_PROVIDER in ("gemini", "google"):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            llm = ChatGoogleGenerativeAI(
                model=GEMINI_MODEL,
                google_api_key=GOOGLE_API_KEY,
                temperature=0.0,
            ).with_structured_output(WorkflowPlan)
            out = llm.invoke(sys_prompt)
            if out:
                return out.model_dump()
        except Exception:
            pass

    if OPENAI_API_KEY and LLM_PROVIDER == "openai":
        try:
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                model=OPENAI_MODEL,
                api_key=OPENAI_API_KEY,
                temperature=0.0,
            ).with_structured_output(WorkflowPlan)
            out = llm.invoke(sys_prompt)
            if out:
                return out.model_dump()
        except Exception:
            pass

    return None


def get_deterministic_plan(prompt: str) -> dict[str, Any]:
    """
    Deterministic rule-based planning fallback that runs completely offline with zero API keys.
    Accurately handles predefined vs dynamic DAG composition, schedule extraction, and parameter parsing.
    """
    lower = prompt.lower()
    sched = parse_schedule_expression(prompt)

    email_m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", prompt)
    recipient = email_m.group(0) if email_m else (DEFAULT_OPS_EMAIL if ("operation" in lower or "ops" in lower) else None)

    hours_m = re.search(r"(?:last|past)\s+(\d+)\s*(?:hours?|hrs?)", lower)
    hours = int(hours_m.group(1)) if hours_m else 6

    mins_m = re.search(r"(?:more than|over|>)\s*(\d+)\s*(?:minutes?|mins?)", lower)
    min_active = int(mins_m.group(1)) if mins_m else 0

    wants_perf = any(k in lower for k in ["performance", "uptime", "latency", "link stats"])
    wants_summary = any(k in lower for k in ["summary", "summarize", "summaries"])
    wants_ticket = any(k in lower for k in ["ticket", "jira", "servicenow", "incident"])
    wants_email = any(k in lower for k in ["email", "mail", "send report"])

    if wants_perf:
        loc_m = re.search(r"for\s+([A-Za-z]+)", prompt, re.IGNORECASE)
        loc = loc_m.group(1) if loc_m and loc_m.group(1).lower() not in {"all", "last", "the"} else None
        steps = [
            {
                "name": "collect_performance",
                "plugin": "performance_source",
                "condition": "always",
                "params": {"location": loc, "hours": hours},
            }
        ]
        if wants_email:
            steps.append(
                {
                    "name": "email_report",
                    "plugin": "email_notifier",
                    "condition": "always",
                    "params": {
                        "recipient": recipient or DEFAULT_OPS_EMAIL,
                        "subject": f"Performance Report - {loc or 'All'} ({hours}h)",
                    },
                }
            )
            return {
                "mode": "dynamic",
                "workflow_code": f"WF_DYN_{uuid.uuid4().hex[:6].upper()}",
                "workflow_name": f"Performance Report & Email ({loc or 'All'})",
                "workflow_description": "Dynamic workflow: collect performance stats and email report.",
                "steps": steps,
                "extracted_params": {"location": loc, "hours": hours, "recipient": recipient},
                "is_scheduled": sched is not None,
                "schedule": sched,
            }
        return {
            "mode": "predefined",
            "workflow_code": "WF004",
            "workflow_name": "Performance Report",
            "workflow_description": "Collect performance stats.",
            "steps": steps,
            "extracted_params": {"location": loc, "hours": hours},
            "is_scheduled": sched is not None,
            "schedule": sched,
        }

    # Ticket priority detection vs alert intensity detection
    priority = "HIGH"
    if "critical" in lower:
        priority = "CRITICAL"
    elif "low-priority" in lower or "low priority" in lower:
        priority = "LOW"
    elif "medium-priority" in lower or "medium priority" in lower:
        priority = "MEDIUM"

    # Remove priority modifier to avoid confusing priority with alert severity
    intensity_text = re.sub(r"\b(high|critical|medium|low)[\s-]priority\b", "", lower)

    intensities = []
    for lvl in ("DOWN", "HIGH", "MEDIUM", "STOPPED"):
        if re.search(r"\b" + lvl.lower() + r"\b", intensity_text):
            intensities.append(lvl)

    unresolved = any(k in lower for k in ["unresolved", "unacknowledged"])
    alert_params = {"intensities": intensities, "unresolved_only": unresolved, "min_active_minutes": min_active}

    # Complex multi-step requests compose dynamic DAG
    if sum([wants_summary, wants_ticket, wants_email]) >= 2:
        steps = [
            {"name": "collect_alerts", "plugin": "alert_source", "condition": "always", "params": alert_params}
        ]
        if wants_summary:
            steps.append(
                {"name": "summarize_alerts", "plugin": "alert_summarizer", "condition": "always", "params": {}}
            )
        if wants_ticket:
            crit_only = "critical" in lower
            steps.append(
                {
                    "name": "create_tickets",
                    "plugin": "jira_ticketing",
                    "condition": "critical_count > 0" if crit_only else "alert_count > 0",
                    "params": {
                        "priority": "CRITICAL" if crit_only else priority,
                        "provider": "jira",
                        "critical_only": crit_only,
                    },
                }
            )
        if wants_email:
            steps.append(
                {
                    "name": "email_report",
                    "plugin": "email_notifier",
                    "condition": "always",
                    "params": {
                        "recipient": recipient or DEFAULT_OPS_EMAIL,
                        "subject": "Daily Operational Alert Report",
                    },
                }
            )
        return {
            "mode": "dynamic",
            "workflow_code": f"WF_DYN_{uuid.uuid4().hex[:6].upper()}",
            "workflow_name": "Dynamic Alert Triage & Notification",
            "workflow_description": "Dynamically generated conditional alert triage workflow.",
            "steps": steps,
            "extracted_params": {**alert_params, "recipient": recipient},
            "is_scheduled": sched is not None,
            "schedule": sched,
        }

    # Single-stage ticketing matches WF002
    if wants_ticket:
        return {
            "mode": "predefined",
            "workflow_code": "WF002",
            "workflow_name": "Ticket Creation",
            "workflow_description": "Create Jira tickets for down devices.",
            "steps": [
                {"name": "collect_alerts", "plugin": "alert_source", "condition": "always", "params": alert_params},
                {
                    "name": "create_tickets",
                    "plugin": "jira_ticketing",
                    "condition": "alert_count > 0",
                    "params": {"priority": priority, "provider": "jira"},
                },
            ],
            "extracted_params": {**alert_params, "priority": priority},
            "is_scheduled": sched is not None,
            "schedule": sched,
        }

    # Default to WF001
    return {
        "mode": "predefined",
        "workflow_code": "WF001",
        "workflow_name": "Daily Alert Summary",
        "workflow_description": "Collect and summarize alerts.",
        "steps": [
            {"name": "collect_alerts", "plugin": "alert_source", "condition": "always", "params": alert_params},
            {"name": "summarize_alerts", "plugin": "alert_summarizer", "condition": "always", "params": {}},
        ],
        "extracted_params": alert_params,
        "is_scheduled": sched is not None,
        "schedule": sched,
    }
