from typing import Any, TypedDict
from pydantic import BaseModel, Field


class StepSpec(BaseModel):
    name: str
    plugin: str
    condition: str = "always"
    params: dict[str, Any] = Field(default_factory=dict)


class ScheduleSpec(BaseModel):
    schedule_type: str  # daily | weekly | monthly | cron
    cron_expression: str


class WorkflowPlan(BaseModel):
    mode: str  # predefined | dynamic
    workflow_code: str
    workflow_name: str
    workflow_description: str
    steps: list[StepSpec]
    extracted_params: dict[str, Any] = Field(default_factory=dict)
    is_scheduled: bool = False
    schedule: ScheduleSpec | None = None


class AutomationState(TypedDict, total=False):
    user_prompt: str
    trigger_type: str  # chat | manual | schedule
    execute_now: bool
    forced_workflow_code: str | None
    forced_params: dict[str, Any]
    schedule_id: int | None
    selected_mode: str
    workflow_id: int | None
    workflow_code: str
    workflow_name: str
    workflow_steps: list[dict[str, Any]]
    extracted_params: dict[str, Any]
    is_scheduled: bool
    schedule_spec: dict[str, Any] | None
    registered_schedule: dict[str, Any] | None
    selected_plugins: list[dict[str, Any]]
    validation_errors: list[str]
    execution_id: int | None
    step_results: list[dict[str, Any]]
    shared_context: dict[str, Any]
    final_report: str
    status: str
