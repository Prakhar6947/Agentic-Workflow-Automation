from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    prompt: str = Field(..., description="Natural language workflow prompt or schedule request")
    execute_now: bool = Field(default=True, description="Whether to immediately run the workflow if scheduled")


class ManualRunRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict, description="Runtime parameters override for workflow steps")


class ScheduleCreateRequest(BaseModel):
    workflow_code: str
    name: str
    schedule_type: str = "daily"
    cron_expression: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class WorkflowStepSchema(BaseModel):
    name: str
    plugin: str
    condition: str = "always"
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinitionSchema(BaseModel):
    steps: list[WorkflowStepSchema]
