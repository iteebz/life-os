from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATE_PATH = Path.home() / ".life" / "steward_loop_state.json"


@dataclass
class LoopState:
    consecutive_code_only_sessions: int = 0
    last_required_task_id: str | None = None
    last_session_outcome: str | None = None
    last_flags: list[str] = field(default_factory=list)


def load_loop_state(path: Path = STATE_PATH) -> LoopState:
    if not path.exists():
        return LoopState()
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return LoopState()
    return LoopState(
        consecutive_code_only_sessions=int(payload.get("consecutive_code_only_sessions", 0)),
        last_required_task_id=payload.get("last_required_task_id"),
        last_session_outcome=payload.get("last_session_outcome"),
        last_flags=list(payload.get("last_flags", [])),
    )


def save_loop_state(state: LoopState, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2) + "\n")


def require_real_world_closure(state: LoopState) -> bool:
    return state.consecutive_code_only_sessions >= 2


def update_loop_state(
    state: LoopState,
    *,
    shipped_code: bool,
    shipped_life: bool,
    flags: list[str],
    required_task_id: str | None,
    outcome: str,
) -> LoopState:
    if shipped_code and not shipped_life:
        state.consecutive_code_only_sessions += 1
    elif shipped_life:
        state.consecutive_code_only_sessions = 0

    state.last_required_task_id = required_task_id
    state.last_session_outcome = outcome
    state.last_flags = list(flags)
    return state


__all__ = [
    "STATE_PATH",
    "LoopState",
    "load_loop_state",
    "require_real_world_closure",
    "save_loop_state",
    "update_loop_state",
]
