from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base, utcnow


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    workflow_type: Mapped[str] = mapped_column(String(30), default="predefined")  # predefined | dynamic
    definition_json: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    executions: Mapped[list["WorkflowExecution"]] = relationship(back_populates="workflow")
    schedules: Mapped[list["Schedule"]] = relationship(back_populates="workflow")


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    schedule_type: Mapped[str] = mapped_column(String(30))  # daily | weekly | monthly | cron
    cron_expression: Mapped[str] = mapped_column(String(100))
    parameters_json: Mapped[str] = mapped_column(Text, default="{}")
    prompt_origin: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workflow: Mapped["Workflow"] = relationship(back_populates="schedules")
    executions: Mapped[list["WorkflowExecution"]] = relationship(back_populates="schedule")


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int | None] = mapped_column(ForeignKey("workflows.id"), nullable=True)
    schedule_id: Mapped[int | None] = mapped_column(ForeignKey("schedules.id"), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(30), default="chat")  # chat | manual | schedule
    user_prompt: Mapped[str] = mapped_column(Text, default="")
    extracted_params_json: Mapped[str] = mapped_column(Text, default="{}")
    selected_plugins_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(30), default="running")  # running | completed | failed
    final_report: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workflow: Mapped["Workflow | None"] = relationship(back_populates="executions")
    schedule: Mapped["Schedule | None"] = relationship(back_populates="executions")
    step_logs: Mapped[list["ExecutionStepLog"]] = relationship(
        back_populates="execution", cascade="all, delete-orphan", order_by="ExecutionStepLog.step_index"
    )
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="execution")
    emails: Mapped[list["EmailLog"]] = relationship(back_populates="execution")


class ExecutionStepLog(Base):
    __tablename__ = "execution_step_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("workflow_executions.id"), index=True)
    step_index: Mapped[int] = mapped_column(Integer)
    step_name: Mapped[str] = mapped_column(String(120))
    plugin_name: Mapped[str] = mapped_column(String(80))
    condition_expr: Mapped[str | None] = mapped_column(String(255), nullable=True)
    condition_met: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30))  # completed | skipped | failed
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    execution: Mapped["WorkflowExecution"] = relationship(back_populates="step_logs")


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_key: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    execution_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_executions.id"), nullable=True)
    alert_uid: Mapped[str] = mapped_column(String(255), index=True)
    device: Mapped[str] = mapped_column(String(150))
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    priority: Mapped[str] = mapped_column(String(30), default="HIGH")
    provider: Mapped[str] = mapped_column(String(40), default="jira")
    summary: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    execution: Mapped["WorkflowExecution | None"] = relationship(back_populates="tickets")


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_executions.id"), nullable=True)
    recipient: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="SENT")  # SENT | SENT_LOGGED | SENT_SMTP
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    execution: Mapped["WorkflowExecution | None"] = relationship(back_populates="emails")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    execution_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_executions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
