from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_SEEN_PATH = Path(__file__).resolve().parents[1] / "state" / "seen_done_threads.json"


@dataclass(slots=True)
class SeenState:
    baseline_created_at: float = 0.0
    completed_before: float = 0.0
    seen_turns: set[str] = field(default_factory=set)
    needs_baseline: bool = False


def review_key(thread_id: str, turn_id: str = "") -> str:
    thread_id = thread_id.strip()
    turn_id = turn_id.strip()
    return f"{thread_id}:{turn_id}" if turn_id else thread_id


def load_seen_state(path: Path = DEFAULT_SEEN_PATH) -> SeenState:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return SeenState(needs_baseline=True)

    if data.get("schema_version") != 2:
        return SeenState(needs_baseline=True)

    raw_turns = data.get("seen_turns", {})
    if isinstance(raw_turns, dict):
        seen_turns = {key for key in raw_turns if isinstance(key, str) and key}
    elif isinstance(raw_turns, list):
        seen_turns = {item for item in raw_turns if isinstance(item, str) and item}
    else:
        seen_turns = set()

    fallback = data.get("fallback_baseline") or {}
    if not isinstance(fallback, dict):
        fallback = {}

    return SeenState(
        baseline_created_at=float(data.get("baseline_created_at") or 0),
        completed_before=float(fallback.get("completed_before") or 0),
        seen_turns=seen_turns,
    )


def save_seen_state(state: SeenState, path: Path = DEFAULT_SEEN_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 2,
        "baseline_created_at": state.baseline_created_at or time.time(),
        "fallback_baseline": {"completed_before": state.completed_before},
        "seen_turns": {key: True for key in sorted(state.seen_turns)},
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_seen(state: SeenState, thread_id: str, turn_id: str, updated_at: float) -> bool:
    if updated_at <= state.completed_before:
        return True
    return review_key(thread_id, turn_id) in state.seen_turns


def mark_seen(thread_id: str, turn_id: str = "", path: Path = DEFAULT_SEEN_PATH) -> bool:
    if not thread_id:
        return False
    state = load_seen_state(path)
    key = review_key(thread_id, turn_id)
    if key in state.seen_turns:
        return False
    state.seen_turns.add(key)
    save_seen_state(state, path)
    return True
