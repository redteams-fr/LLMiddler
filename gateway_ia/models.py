from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    ERROR = "error"


class Session(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Request
    method: str
    path: str
    query_string: str = ""
    request_headers: dict[str, str] = {}
    request_body: bytes | None = None

    # Response
    status_code: int | None = None
    response_headers: dict[str, str] = {}
    response_body: bytes | None = None
    is_streaming: bool = False

    # Metadata
    status: SessionStatus = SessionStatus.PENDING
    duration_ms: float | None = None
    error_message: str | None = None

    model_config = {"arbitrary_types_allowed": True}
