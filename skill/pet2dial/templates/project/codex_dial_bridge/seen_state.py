from __future__ import annotations

import json
from pathlib import Path


DEFAULT_SEEN_PATH = Path(__file__).resolve().parents[1] / "state" / "seen_done_threads.json"


def load_seen(path: Path = DEFAULT_SEEN_PATH) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()

    thread_ids = data.get("thread_ids", [])
    if not isinstance(thread_ids, list):
        return set()
    return {item for item in thread_ids if isinstance(item, str) and item}


def save_seen(thread_ids: set[str], path: Path = DEFAULT_SEEN_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"thread_ids": sorted(thread_ids)}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mark_seen(thread_id: str, path: Path = DEFAULT_SEEN_PATH) -> bool:
    if not thread_id:
        return False
    thread_ids = load_seen(path)
    if thread_id in thread_ids:
        return False
    thread_ids.add(thread_id)
    save_seen(thread_ids, path)
    return True
