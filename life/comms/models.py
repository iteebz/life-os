from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Account:
    id: str
    service_type: str
    provider: str
    email: str
    auth_data: str | None
    enabled: bool
    created_at: datetime


@dataclass(frozen=True)
class Draft:
    id: str
    thread_id: str | None
    to_addr: str
    cc_addr: str | None
    subject: str | None
    body: str
    claude_reasoning: str | None
    from_account_id: str | None
    from_addr: str | None
    created_at: datetime
    approved_at: datetime | None
    sent_at: datetime | None
