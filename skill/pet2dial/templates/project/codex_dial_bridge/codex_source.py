from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .protocol import Bubble, DialState, MAX_BUBBLES
from .seen_state import load_seen, save_seen

TITLE_MAX = 34
DEFAULT_CODEX_HOME = Path.home() / ".codex"


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
        return "proofwarden"
    return sorted(candidates, reverse=True)[0][1]


def ui_selected_pet_id(codex_home: Path | None = None) -> str:
    home = codex_home or DEFAULT_CODEX_HOME
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
        display_state = "review" if self.state == "done" else self.state
        return Bubble(
            thread_id=self.thread_id,
            title=self.title,
            state=display_state,
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
                    elif event_type == "task_complete":
                        state = "done"
                        turn_id = payload.get("turn_id", turn_id)
                    elif event_type == "turn_aborted":
                        state = "aborted"
                        turn_id = payload.get("turn_id", turn_id)
                    elif event_type in {"agent_message_delta", "exec_command_begin", "token_count"}:
                        if state not in {"done", "aborted"}:
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
        seen_done_threads = load_seen(self.seen_path) if self.seen_path else load_seen()
        cleaned_seen = False
        for path in self.session_paths()[: max(48, limit * 6)]:
            summary = summarize_session(path)
            if summary:
                if summary.state == "running" and summary.thread_id in seen_done_threads:
                    seen_done_threads.remove(summary.thread_id)
                    cleaned_seen = True
                if summary.state not in {"running", "done"}:
                    continue
                if summary.state == "done" and summary.thread_id in seen_done_threads:
                    continue
                summaries.append(summary)
            if len(summaries) >= limit:
                break

        if cleaned_seen:
            save_seen(seen_done_threads, self.seen_path) if self.seen_path else save_seen(seen_done_threads)

        mode = "idle"
        if any(item.state == "running" for item in summaries):
            mode = "running"
        elif any(item.state == "done" for item in summaries):
            mode = "review"

        return DialState(
            pet=self.current_pet(),
            mode=mode,
            now=time.time(),
            bubbles=[item.to_bubble() for item in summaries[:limit]],
        )
