from __future__ import annotations
import uuid
from datetime import UTC, datetime
from enum import Enum
from sqlmodel import Field, SQLModel

class ApprovalStatus(str, Enum):
    PENDING="pending"; APPROVED="approved"; REJECTED="rejected"

class ApprovalTask(SQLModel, table=True):
    __tablename__="approval_tasks"
    id: str = Field(default_factory=lambda:str(uuid.uuid4()), primary_key=True)
    contract_id: str = Field(foreign_key="contracts.id", index=True)
    requester_id: str = Field(foreign_key="users.id", index=True)
    reviewer_id: str | None = Field(default=None, foreign_key="users.id", index=True)
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING, index=True)
    comment: str = Field(default="", max_length=1000)
    created_at: datetime = Field(default_factory=lambda:datetime.now(UTC))
    decided_at: datetime | None = None
