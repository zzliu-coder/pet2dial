from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .protocol import Bubble, DialState, MAX_BUBBLES
from .seen_state import DEFAULT_SEEN_PATH, SeenState, is_seen, load_seen_state, review_key, save_seen_state

TITLE_MAX = 34
DEFAULT_CODEX_HOME = Path.home() / ".codex"
FAILED_WINDOW_SECONDS = 300
WAITING_WINDOW_SECONDS = 1800
WAITING_EVENT_TYPES = {
    "approval_request",
    "request_user_input",
    "user_input_requested",
    "waiting_on_approval",
    "waiting_on_user_input",
}
STATE_PRIORITY = {
    "waiting": 0,
    "failed": 1,
    "review": 2,
    "running": 3,
}


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts)


def _is_real_user_text(text: str) -> bool:
    stripped = text.lstrip()
    return bool(
        stripped
        and not stripped.startswith("# AGENTS.md instructions")
        and not stripped.startswith("<turn_aborted>")
        and "<environment_context>" not in stripped
    )


def compact_title(value: str, max_chars: int = TITLE_MAX) -> str:
    value = re.sub(r"\[\$?([^\]]+)\]\([^)]+\)", r"\1", value)
    title = " ".join(value.split())
    if len(title) <= max_chars:
        return title
    return title[: max_chars - 1] + "…"


def thread_id_from_path(path: Path) -> str:
    name = path.name.removesuffix(".jsonl")
    parts = name.split("-")
    if len(parts) >= 6:
        return "-".join(parts[-5:])
    return ""


def newest_pet_id(codex_home: Path | None = None) -> str:
    home = codex_home or DEFAULT_CODEX_HOME
    pets_dir = home / "pets"
    candidates: list[tuple[float, str]] = []
    if pets_dir.exists():
        for manifest in pets_dir.glob("*/pet.json"):
            spritesheet = manifest.parent / "spritesheet.webp"
            if spritesheet.exists():
                candidates.append((max(manifest.stat().st_mtime, spritesheet.stat().st_mtime), manifest.parent.name))
    if not candidates:
        return ""
    return sorted(candidates, reverse=True)[0][1]


def ui_selected_pet_id(codex_home: Path | None = None) -> str:
    home = codex_home or DEFAULT_CODEX_HOME
    config_path = home / "config.toml"
    try:
        config_text = config_path.read_text(encoding="utf-8")
    except OSError:
        config_text = ""
    match = re.search(r'(?m)^\s*selected-avatar-id\s*=\s*"custom:([^"]+)"', config_text)
    if match:
        pet_id = match.group(1)
        pet_dir = home / "pets" / pet_id
        if (pet_dir / "pet.json").exists() and (pet_dir / "spritesheet.webp").exists():
            return pet_id

    path = home / ".codex-global-state.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""

    persisted = data.get("electron-persisted-atom-state")
    if not isinstance(persisted, dict):
        return ""

    avatar_ids = persisted.get("first-awake-pet-notification-avatar-ids")
    if not isinstance(avatar_ids, list):
        return ""

    for value in reversed(avatar_ids):
        if not isinstance(value, str) or not value.startswith("custom:"):
            continue
        pet_id = value.split(":", 1)[1]
        pet_dir = home / "pets" / pet_id
        if (pet_dir / "pet.json").exists() and (pet_dir / "spritesheet.webp").exists():
            return pet_id
    return ""


@dataclass(slots=True)
class SessionSummary:
    thread_id: str
    title: str
    state: str
    updated_at: float
    cwd: str = ""
    turn_id: str = ""

    def to_bubble(self) -> Bubble:
        return Bubble(
            thread_id=self.thread_id,
            title=self.title,
            state=self.state,
            updated_at=self.updated_at,
            cwd=self.cwd,
            turn_id=self.turn_id,
        )


def summarize_session(path: Path) -> SessionSummary | None:
    thread_id = thread_id_from_path(path)
    if not thread_id:
        return None

    cwd = ""
    title = ""
    state = "running"
    turn_id = ""
    updated_at = path.stat().st_mtime

    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                try:
                    item = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                timestamp = item.get("timestamp")
                if isinstance(timestamp, str):
                    # File mtime is the stable ordering source; timestamp parsing is optional.
                    updated_at = path.stat().st_mtime

                if item.get("type") == "session_meta":
                    payload = item.get("payload") or {}
                    cwd = payload.get("cwd") or cwd
                    continue

                if item.get("type") == "response_item":
                    payload = item.get("payload") or {}
                    if payload.get("type") == "message" and payload.get("role") == "user":
                        text = _content_text(payload.get("content"))
                        if _is_real_user_text(text):
                            if not title:
                                title = compact_title(text)
                            state = "running"
                            turn_id = ""
                    continue

                if item.get("type") == "event_msg":
                    payload = item.get("payload") or {}
                    event_type = payload.get("type")
                    if event_type == "user_message":
                        text = payload.get("message", "")
                        if _is_real_user_text(text):
                            if not title:
                                title = compact_title(text)
                            state = "running"
                            turn_id = ""
                    elif event_type in WAITING_EVENT_TYPES:
                        state = "waiting"
                        turn_id = payload.get("turn_id", turn_id)
                    elif event_type == "task_complete":
                        state = "review"
                        turn_id = payload.get("turn_id", turn_id)
                    elif event_type in {"turn_aborted", "task_failed", "task_cancelled"}:
                        state = "failed"
                        turn_id = payload.get("turn_id", turn_id)
                    elif event_type in {"task_started", "agent_message_delta", "exec_command_begin", "token_count"}:
                        if state not in {"waiting", "review", "failed"}:
                            state = "running"
    except OSError:
        return None

    if not title:
        title = compact_title(Path(cwd).name if cwd else thread_id[:8])
    return SessionSummary(thread_id=thread_id, title=title, state=state, updated_at=updated_at, cwd=cwd, turn_id=turn_id)


class CodexSource:
    def __init__(self, codex_home: Path | None = None, pet: str = "auto", seen_path: Path | None = None):
        self.codex_home = codex_home or DEFAULT_CODEX_HOME
        self.pet = pet
        self.sessions_dir = self.codex_home / "sessions"
        self.seen_path = seen_path

    def resolved_seen_path(self) -> Path:
        return self.seen_path or DEFAULT_SEEN_PATH

    def current_pet(self) -> str:
        if self.pet == "auto":
            return ui_selected_pet_id(self.codex_home) or newest_pet_id(self.codex_home)
        return self.pet

    def session_paths(self) -> list[Path]:
        if not self.sessions_dir.exists():
            return []
        return sorted(
            self.sessions_dir.glob("*/*/*/rollout-*.jsonl"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )

    def snapshot(self, limit: int = MAX_BUBBLES) -> DialState:
        summaries: list[SessionSummary] = []
        seen_path = self.resolved_seen_path()
        seen_state = load_seen_state(seen_path)
        now = time.time()
        for path in self.session_paths()[: max(48, limit * 6)]:
            summary = summarize_session(path)
            if summary:
                if summary.state not in {"waiting", "failed", "running", "review"}:
                    continue
                summaries.append(summary)

        if seen_state.needs_baseline:
            seen_state = SeenState(
                baseline_created_at=now,
                completed_before=now,
                seen_turns={review_key(item.thread_id, item.turn_id) for item in summaries if item.state == "review"},
            )
            save_seen_state(seen_state, seen_path)

        filtered: list[SessionSummary] = []
        for summary in summaries:
            if summary.state == "waiting" and now - summary.updated_at > WAITING_WINDOW_SECONDS:
                continue
            if summary.state == "failed" and now - summary.updated_at > FAILED_WINDOW_SECONDS:
                continue
            if summary.state == "review" and is_seen(seen_state, summary.thread_id, summary.turn_id, summary.updated_at):
                continue
            filtered.append(summary)

        filtered.sort(key=lambda item: (STATE_PRIORITY.get(item.state, 99), -item.updated_at))
        counts = {state: 0 for state in STATE_PRIORITY}
        for item in filtered:
            counts[item.state] = counts.get(item.state, 0) + 1

        mode = "idle"
        if counts["waiting"]:
            mode = "waiting"
        elif counts["failed"]:
            mode = "failed"
        elif counts["review"]:
            mode = "review"
        elif counts["running"]:
            mode = "running"

        return DialState(
            pet=self.current_pet(),
            mode=mode,
            now=now,
            counts=counts,
            bubbles=[item.to_bubble() for item in filtered[:limit]],
        )

    def mark_current_reviews_seen(self) -> int:
        seen_path = self.resolved_seen_path()
        seen_state = load_seen_state(seen_path)
        before = len(seen_state.seen_turns)
        now = time.time()
        seen_state.baseline_created_at = seen_state.baseline_created_at or now
        seen_state.completed_before = max(seen_state.completed_before, now)
        for path in self.session_paths():
            summary = summarize_session(path)
            if not summary:
                continue
            if summary.state == "review":
                seen_state.seen_turns.add(review_key(summary.thread_id, summary.turn_id))
        save_seen_state(seen_state, seen_path)
        return len(seen_state.seen_turns) - before
