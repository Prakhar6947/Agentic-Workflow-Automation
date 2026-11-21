# Agentic Workflow Automation Engine

An autonomous, multi-agent workflow orchestration engine powered by **LangGraph**, **FastAPI**, **SQLAlchemy**, and **APScheduler**.

The system translates natural-language prompts into structured, conditional workflow DAGs (directed acyclic graphs), executes extensible plugins with deterministic schema validation, schedules recurring cron jobs, manages incident tickets and email outboxes, and synthesizes Markdown reports.

---

## Architecture Diagram

```text
User Prompt / Schedule Trigger
              │
              ▼
┌───────────────────────────┐
│  Workflow Selection Agent │  ← Matches WF001–WF004 or composes Dynamic DAG (WF_DYN_...)
└────────────┬──────────────┘
             │ (validates params & detects cron / daily / weekly / monthly schedule)
             ▼
┌───────────────────────────┐
│   Plugin Selection Agent  │  ← Resolves & validates Pydantic schemas via PluginRegistry
└─────┬──────────────┬──────┘
      │ (scheduled)  │ (immediate)
      ▼              │
┌──────────────────┐ │
│ Schedule Node    │ │  ← Persists to SQL schedules & registers APScheduler CronTrigger
└────────┬─────────┘ │
         ▼           ▼
┌───────────────────────────┐
│      Execution Agent      │  ← Evaluates safe AST step conditions & runs plugins in order
└────────────┬──────────────┘
             │ (persists workflow_executions, execution_step_logs, tickets, email_logs)
             ▼
┌───────────────────────────┐
│      Reporting Agent      │  ← Synthesizes final Markdown report & updates execution log
└───────────────────────────┘
```

---

## Key Features

1. **LangGraph Multi-Agent Pipeline**:
   - `Workflow Selection Agent`: Uses Gemini/OpenAI structured output or an offline deterministic fallback to classify requests into predefined workflows (`WF001`–`WF004`) or dynamically synthesize a multi-step DAG (`WF_DYN_...`).
   - `Plugin Selection Agent`: Validates step parameters against Pydantic models.
   - `Schedule Registration Node`: Registers APScheduler cron triggers and writes to SQL `schedules`.
   - `Execution Agent`: Evaluates AST conditions and dispatches plugin execution.
   - `Reporting Agent`: Produces structured markdown execution reports.

2. **Predefined Workflows (`WF001`–`WF004`)**:
   - `WF001` (`Daily Alert Summary`): Collect and summarize operational alerts.
   - `WF002` (`Ticket Creation`): Collect alerts and create prioritized incident tickets.
   - `WF003` (`Email Notification`): Send notifications for reports and operational alerts.
   - `WF004` (`Performance Report`): Extract network link performance metrics and KPIs.

3. **Dynamically Generated Workflows**:
   - Multi-stage natural language prompts (e.g. alert triage + summarization + conditional ticketing + email distribution) are automatically composed into a dynamic DAG (`WF_DYN_...`) and persisted to SQL.

4. **Conditional Workflows (Safe AST Evaluation)**:
   - Evaluates step conditions (`always`, `alert_count > 0`, `critical_count > 0`, `down_links > 0`) using Python's `ast` module (no `eval()` or `exec()`).
   - Unmet conditions skip the step with explicit audit trail entries in `execution_step_logs`.

5. **Extensible Plugin Registry**:
   - Built on `BasePlugin` and `@registry.register`.
   - `alert_source`: Filters telemetry alerts (`alerts.json`).
   - `alert_summarizer`: Synthesizes breakdown of alerts by severity.
   - `jira_ticketing`: Generates prioritized incident tickets with deduplication and external reference tracking.
   - `performance_source`: Computes network link uptime, latency, and performance scores (`performance_stats.json`).
   - `email_notifier`: Dispatches emails via SMTP (or fallback logged) and records to `email_logs`.

6. **Relational Database Design (SQLAlchemy)**:
   - Stores operational metadata in SQL: `workflows`, `schedules`, `workflow_executions`, `execution_step_logs`, `tickets`, `email_logs`, `chat_messages`.
   - Telemetry data remains decoupled in `data/alerts.json` and `data/performance_stats.json`.

7. **Scheduled Execution**:
   - Real-time APScheduler cron triggers backed by SQL schedules.
   - Supports daily, weekly, monthly, and custom crontabs.

8. **Offline Fallback & LLM Planning**:
   - Zero-configuration deterministic execution mode out-of-the-box.
   - Optional Google Gemini (`GOOGLE_API_KEY`) or OpenAI (`OPENAI_API_KEY`) structured output.

---

## Project Structure

```text
.
├── README.md
├── requirements.txt
├── .env.example
├── .env
├── alerts.json
├── performance_stats.json
├── db.py                       # Root export for standalone imports
├── plugins.py                  # Root export for standalone imports
├── scheduler.py                # Root export for standalone imports
├── agents.py                   # Root export for standalone imports
├── main.py                     # Root export for standalone imports
├── data/
│   ├── alerts.json             # Operational alert telemetry (9 alerts)
│   └── performance_stats.json  # Network link performance telemetry (152 links)
├── app/
│   ├── __init__.py
│   ├── config.py               # Environment configuration
│   ├── main.py                 # FastAPI application & lifespan
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py         # SQLAlchemy engine & session factory
│   │   ├── models.py           # SQL ORM models
│   │   └── seed.py             # Predefined workflows seeder (WF001–WF004)
│   ├── plugins/
│   │   ├── __init__.py
│   │   ├── base.py             # BasePlugin abstract base class
│   │   ├── registry.py         # PluginRegistry & singleton instance
│   │   ├── alert_plugin.py     # alert_source plugin
│   │   ├── summary_plugin.py   # alert_summarizer plugin
│   │   ├── ticket_plugin.py    # jira_ticketing plugin
│   │   ├── performance_plugin.py # performance_source plugin
│   │   └── email_plugin.py     # email_notifier plugin
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── state.py            # TypedDict state & Pydantic schemas
│   │   ├── condition_eval.py   # Safe AST condition evaluator
│   │   ├── llm.py              # LLM structured output & deterministic fallback
│   │   ├── workflow_selector.py # Workflow selection agent
│   │   ├── plugin_selector.py  # Plugin selection agent
│   │   ├── executor.py         # Step execution agent
│   │   ├── reporter.py         # Report generation agent
│   │   └── graph.py            # LangGraph state machine assembly
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── service.py          # APScheduler cron service
│   ├── api/
│   │   ├── __init__.py
│   │   ├── schemas.py          # Request/response Pydantic schemas
│   │   └── routes.py           # REST endpoints
│   └── static/
│       └── index.html          # Interactive Web Dashboard UI
└── tests/
    ├── __init__.py
    └── test_engine.py          # Comprehensive test suite (11 test cases)
```

---

## Quick Start

### 1. Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# (Optional) Configure environment
cp .env.example .env
```

### 2. Run Application

```bash
# Using uvicorn (either path works)
uvicorn app.main:app --reload --port 8000
# OR
uvicorn main:app --reload --port 8000
```

- **Interactive Dashboard**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Swagger API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 3. Run Test Suite

```bash
pytest -v
```

---

## Verification of the 3 Assignment Prompts

### Prompt 1: Scheduled + Dynamic + Conditional Alert Triage

**Prompt**:
> *"Every day at 9 AM, check all unresolved down and high operational alerts, generate a summary, create a ticket for each critical incident and email the report to the operations team."*

**API Call**:
```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Every day at 9 AM, check all unresolved down and high operational alerts, generate a summary, create a ticket for each critical incident and email the report to the operations team."}'
```

**Execution Behavior**:
1. **Schedule Registered**: Daily cron trigger `0 9 * * *` saved in SQL `schedules` and registered in APScheduler.
2. **Dynamic Workflow Generated**: Composes DAG `WF_DYN_...`:
   - Step 1: `collect_alerts` (`alert_source`, `intensities=['DOWN', 'HIGH']`, `unresolved_only=True`)
   - Step 2: `summarize_alerts` (`alert_summarizer`, condition: `always`)
   - Step 3: `create_tickets` (`jira_ticketing`, condition: `critical_count > 0`, `priority='CRITICAL'`)
   - Step 4: `email_report` (`email_notifier`, `recipient='ops-team@company.com'`)
3. **Telemetry Evaluation**:
   - Matches 5 unresolved alerts:
     - `240004-MECCCA-SD-3057` (HIGH)
     - `140093-LAN-10.20.0.252` (DOWN - Critical)
     - `140098-LAN-10.20.0.94` (HIGH)
     - `150351-LAN-10.20.1.13` (DOWN - Critical)
     - `Beccca-Agent-2 (primary)` (HIGH)
   - Excludes resolved alerts (`290004-BANTWAL-3101-D` and `240031-SHIVAMOGGA-426-IPDS`).
   - Condition `critical_count > 0` evaluates to `True` (2 critical alerts).
   - Creates 2 deduplicated CRITICAL Jira tickets in SQL.
   - Logs email to `ops-team@company.com`.

---

### Prompt 2: Predefined Workflow WF002 (Jira Ticketing)

**Prompt**:
> *"Create a high-priority Jira ticket for all devices that have been down for more than 15 minutes."*

**API Call**:
```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create a high-priority Jira ticket for all devices that have been down for more than 15 minutes."}'
```

**Execution Behavior**:
1. **Route Selection**: Matches predefined workflow `WF002` (`Ticket Creation`).
2. **Telemetry Evaluation**:
   - Filters `intensities=['DOWN']`, `min_active_minutes=15`.
   - Identifies all 4 matching DOWN devices:
     - `140093-LAN-10.20.0.252` (5,976 min)
     - `150351-LAN-10.20.1.13` (5,976 min)
     - `290004-BANTWAL-3101-D` (10,276 min, preserves external reference `SR601810`)
     - `240031-SHIVAMOGGA-426-IPDS` (10,276 min, preserves external reference `SR601811`)
3. **Ticketing & Deduplication**:
   - Creates 4 HIGH-priority Jira tickets in SQL.
   - If executed again, deduplication identifies existing open tickets and skips re-creation.

---

### Prompt 3: Dynamic Performance Report & Email Notification

**Prompt**:
> *"Generate the performance report for Mumbai for last 6 hours and email it to test@gmail.com"*

**API Call**:
```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Generate the performance report for Mumbai for last 6 hours and email it to test@gmail.com"}'
```

**Execution Behavior**:
1. **Dynamic Workflow Generated**: Composes DAG `WF_DYN_...` (`performance_source` + `email_notifier`).
2. **Telemetry Evaluation**:
   - Scans 152 links in `data/performance_stats.json`.
   - Evaluates query `Mumbai`: 0 matching links.
   - Report clearly lists 0 matching links, presents available dataset zones (`mangaluru`, `Shivamogga`), and computes the overall baseline metrics (152 links, 52 down, 63.32% avg uptime).
   - If queried for `mangaluru`: returns 82 links, 22 down, 71.07% avg uptime.
   - If queried for `Shivamogga`: returns 70 links, 30 down, 54.25% avg uptime.
3. **Email Notification**:
   - Dispatches and logs report delivery to `test@gmail.com`.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat` (or `/chat`) | Submit natural language workflow prompt |
| `GET` | `/api/workflows` | List predefined and dynamic workflows |
| `POST` | `/api/workflows/{code}/execute` | Manually run workflow with optional params |
| `GET` | `/api/schedules` | List active APScheduler cron schedules |
| `POST` | `/api/schedules` | Create a new recurring cron schedule |
| `POST` | `/api/schedules/{id}/trigger` | Immediately trigger a scheduled job |
| `DELETE`| `/api/schedules/{id}` | Deactivate/remove a schedule |
| `GET` | `/api/executions` | List recent executions and step logs |
| `GET` | `/api/executions/{id}` | Detailed execution audit log with AST evaluations |
| `GET` | `/api/tickets` | List created tickets |
| `GET` | `/api/emails` | List email outbox logs |
| `GET` | `/api/plugins` | List registered plugins and input schemas |
| `GET` | `/health` (or `/api/health`) | Production health check (DB connectivity, scheduler status, uptime) |
| `GET` | `/live` (or `/api/live`) | Kubernetes / container liveness probe |
| `GET` | `/ready` (or `/api/ready`) | Kubernetes / container readiness probe |

---

## Production Deployment & Operations

For complete deployment runbooks across Docker, Kubernetes, AWS ECS, GCP Cloud Run, and Render/Railway, see the **[Production Deployment Guide (DEPLOYMENT.md)](DEPLOYMENT.md)**.

### Quick Docker Production Run

```bash
# Launch multi-container stack (App + PostgreSQL 16)
docker compose up --build -d

# Verify health
curl http://localhost:8000/health
```
