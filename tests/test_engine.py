import json
import pytest
from fastapi.testclient import TestClient
from app.agents.condition_eval import evaluate_condition
from app.agents.graph import automation_graph
from app.db.database import Base, SessionLocal, engine
from app.db.models import EmailLog, Schedule, Ticket, Workflow, WorkflowExecution
from app.db.seed import init_db
from app.main import app
from app.plugins.registry import registry


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)
    init_db()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_predefined_workflows_seeded():
    db = SessionLocal()
    try:
        codes = [w.code for w in db.query(Workflow).all()]
        for expected in ["WF001", "WF002", "WF003", "WF004"]:
            assert expected in codes, f"{expected} should be seeded in workflows table"
    finally:
        db.close()


def test_plugin_registry():
    plugins = registry.list_plugins()
    names = {p["name"] for p in plugins}
    expected_plugins = {"alert_source", "alert_summarizer", "jira_ticketing", "performance_source", "email_notifier"}
    assert expected_plugins.issubset(names), f"Missing plugins: {expected_plugins - names}"


def test_safe_ast_condition_eval():
    ctx = {"alert_count": 5, "critical_count": 2, "down_links": 0, "tickets_created_count": 2}
    assert evaluate_condition("always", ctx) is True
    assert evaluate_condition("true", ctx) is True
    assert evaluate_condition("alert_count > 0", ctx) is True
    assert evaluate_condition("critical_count > 1", ctx) is True
    assert evaluate_condition("down_links > 0", ctx) is False
    assert evaluate_condition("critical_count > 0 and alert_count >= 5", ctx) is True
    assert evaluate_condition("down_links > 0 or critical_count > 0", ctx) is True
    assert evaluate_condition("not down_links > 0", ctx) is True


def test_prompt_1_scheduled_alert_triage():
    prompt = "Every day at 9 AM, check all unresolved down and high operational alerts, generate a summary, create a ticket for each critical incident and email the report to the operations team."
    res = automation_graph.invoke(
        {"user_prompt": prompt, "trigger_type": "chat", "execute_now": True}
    )

    assert res["status"] == "completed"
    assert res["selected_mode"] == "dynamic"
    assert res["workflow_code"].startswith("WF_DYN_")
    assert res["is_scheduled"] is True
    assert res["schedule_spec"]["cron_expression"] == "0 9 * * *"

    ctx = res["shared_context"]
    assert ctx["alert_count"] == 5
    assert ctx["critical_count"] == 2
    assert len(ctx["created_tickets"]) == 2

    # Check that tickets created were for the down devices
    ticket_devices = [t["device"] for t in ctx["created_tickets"]]
    assert "140093-LAN-10.20.0.252" in ticket_devices
    assert "150351-LAN-10.20.1.13" in ticket_devices

    # Verify email
    email = ctx.get("email_sent")
    assert email is not None
    assert email["recipient"] == "ops-team@company.com"

    # Verify database persistence
    db = SessionLocal()
    try:
        exec_row = db.query(WorkflowExecution).filter(WorkflowExecution.id == res["execution_id"]).first()
        assert exec_row is not None
        assert exec_row.status == "completed"
        assert len(exec_row.step_logs) == 4
    finally:
        db.close()


def test_prompt_2_jira_ticketing_down_devices():
    prompt = "Create a high-priority Jira ticket for all devices that have been down for more than 15 minutes."
    res = automation_graph.invoke(
        {"user_prompt": prompt, "trigger_type": "chat", "execute_now": True}
    )

    assert res["status"] == "completed"
    assert res["workflow_code"] == "WF002"
    assert res["selected_mode"] == "predefined"

    ctx = res["shared_context"]
    # Total DOWN devices with active_since > 15m is 4
    assert ctx["alert_count"] == 4
    assert ctx["critical_count"] == 4

    # Run again to verify ticket deduplication in SQL
    res2 = automation_graph.invoke(
        {"user_prompt": prompt, "trigger_type": "chat", "execute_now": True}
    )
    assert res2["status"] == "completed"
    # Deduplication should ensure 0 new duplicate tickets created
    assert res2["shared_context"]["tickets_created_count"] == 0


def test_prompt_3_performance_report_mumbai():
    prompt = "Generate the performance report for Mumbai for last 6 hours and email it to test@gmail.com"
    res = automation_graph.invoke(
        {"user_prompt": prompt, "trigger_type": "chat", "execute_now": True}
    )

    assert res["status"] == "completed"
    assert res["selected_mode"] == "dynamic"

    ctx = res["shared_context"]
    assert "performance_report" in ctx
    # Mumbai has 0 links in the dataset
    assert "**Matching Links for `Mumbai`:** 0" in ctx["performance_report"]
    assert "**Available Zones in Dataset:** Shivamogga, mangaluru" in ctx["performance_report"]

    # Verify email sent to test@gmail.com
    email = ctx.get("email_sent")
    assert email is not None
    assert email["recipient"] == "test@gmail.com"


def test_performance_report_mangaluru_and_shivamogga():
    # Mangaluru direct query
    res_m = automation_graph.invoke(
        {
            "user_prompt": "Generate performance report for mangaluru",
            "trigger_type": "chat",
            "execute_now": True,
        }
    )
    assert res_m["status"] == "completed"
    ctx_m = res_m["shared_context"]
    assert "**Links Analyzed:** 82 (Down: 22)" in ctx_m["performance_report"]
    assert "**Avg Uptime:** 71.07%" in ctx_m["performance_report"]

    # Shivamogga direct query
    res_s = automation_graph.invoke(
        {
            "user_prompt": "Generate performance report for Shivamogga",
            "trigger_type": "chat",
            "execute_now": True,
        }
    )
    assert res_s["status"] == "completed"
    ctx_s = res_s["shared_context"]
    assert "**Links Analyzed:** 70 (Down: 30)" in ctx_s["performance_report"]
    assert "**Avg Uptime:** 54.25%" in ctx_s["performance_report"]


def test_api_chat_endpoint(client):
    res = client.post("/api/chat", json={"prompt": "Summarize today's operational alerts"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert "report" in data
    assert len(data["step_results"]) >= 1


def test_api_workflows_and_manual_execution(client):
    res = client.get("/api/workflows")
    assert res.status_code == 200
    wfs = res.json()
    assert len(wfs) >= 4

    run_res = client.post("/api/workflows/WF001/execute", json={"params": {}})
    assert run_res.status_code == 200
    assert run_res.json()["status"] == "completed"


def test_api_schedules_crud(client):
    res = client.post(
        "/api/schedules",
        json={
            "workflow_code": "WF001",
            "name": "Test Morning Alert Cron",
            "schedule_type": "daily",
            "cron_expression": "0 8 * * *",
            "parameters": {},
        },
    )
    assert res.status_code == 200
    sched = res.json()
    sched_id = sched["id"]

    list_res = client.get("/api/schedules")
    assert list_res.status_code == 200
    assert any(s["id"] == sched_id for s in list_res.json())

    trig_res = client.post(f"/api/schedules/{sched_id}/trigger")
    assert trig_res.status_code == 200
    assert trig_res.json()["status"] == "completed"

    del_res = client.delete(f"/api/schedules/{sched_id}")
    assert del_res.status_code == 200


def test_api_executions_and_tickets_and_emails(client):
    execs = client.get("/api/executions").json()
    assert len(execs) > 0
    first_id = execs[0]["id"]

    detail = client.get(f"/api/executions/{first_id}").json()
    assert detail["id"] == first_id
    assert "step_logs" in detail

    tickets = client.get("/api/tickets").json()
    assert isinstance(tickets, list)

    emails = client.get("/api/emails").json()
    assert isinstance(emails, list)

    plugins = client.get("/api/plugins").json()
    assert len(plugins) == 5


def test_health_and_observability_probes(client):
    # Test /health
    res_health = client.get("/health")
    assert res_health.status_code == 200
    data = res_health.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["scheduler"] == "running"
    assert "uptime_seconds" in data
    assert data["version"] == "1.0.0"

    # Test /api/health
    res_api_health = client.get("/api/health")
    assert res_api_health.status_code == 200
    assert res_api_health.json()["status"] == "healthy"

    # Test /live
    res_live = client.get("/live")
    assert res_live.status_code == 200
    assert res_live.json()["status"] == "alive"

    # Test /ready
    res_ready = client.get("/ready")
    assert res_ready.status_code == 200
    assert res_ready.json()["status"] == "ready"
