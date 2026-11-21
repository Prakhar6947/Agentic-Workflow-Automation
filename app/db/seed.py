import json
from app.db.database import Base, SessionLocal, engine
from app.db.models import Workflow

PREDEFINED_WORKFLOWS = [
    {
        "code": "WF001",
        "name": "Daily Alert Summary",
        "description": "Collect and summarize operational alerts from telemetry.",
        "steps": [
            {"name": "collect_alerts", "plugin": "alert_source", "condition": "always", "params": {}},
            {"name": "summarize_alerts", "plugin": "alert_summarizer", "condition": "always", "params": {}},
        ],
    },
    {
        "code": "WF002",
        "name": "Ticket Creation",
        "description": "Create prioritized tickets for matching operational alerts.",
        "steps": [
            {"name": "collect_alerts", "plugin": "alert_source", "condition": "always", "params": {}},
            {"name": "create_tickets", "plugin": "jira_ticketing", "condition": "alert_count > 0", "params": {}},
        ],
    },
    {
        "code": "WF003",
        "name": "Email Notification",
        "description": "Send email notifications based on workflow output or conditions.",
        "steps": [
            {"name": "send_email", "plugin": "email_notifier", "condition": "always", "params": {}},
        ],
    },
    {
        "code": "WF004",
        "name": "Performance Report",
        "description": "Collect link performance telemetry and generate regional KPI reports.",
        "steps": [
            {"name": "collect_performance", "plugin": "performance_source", "condition": "always", "params": {}},
        ],
    },
]


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for item in PREDEFINED_WORKFLOWS:
            existing = db.query(Workflow).filter(Workflow.code == item["code"]).first()
            if not existing:
                db.add(
                    Workflow(
                        code=item["code"],
                        name=item["name"],
                        description=item["description"],
                        workflow_type="predefined",
                        definition_json=json.dumps({"steps": item["steps"]}),
                    )
                )
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    print("Database seeded with predefined workflows.")
