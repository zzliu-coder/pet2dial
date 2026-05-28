from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from codex_dial_bridge.codex_source import CodexSource


def write_session(codex_home: Path, thread_id: str, title: str, event_type: str, turn_id: str, mtime: float) -> None:
    session_dir = codex_home / "sessions" / "2026" / "05" / "27"
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / f"rollout-2026-05-27T00-00-00-{thread_id}.jsonl"
    rows = [
        {"type": "session_meta", "payload": {"cwd": f"/tmp/{title}"}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": title}},
    ]
    if event_type:
        rows.append({"type": "event_msg", "payload": {"type": event_type, "turn_id": turn_id}})
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    os.utime(path, (mtime, mtime))


class CodexSourceTests(unittest.TestCase):
    def test_snapshot_counts_and_orders_all_active_states(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex"
            seen_path = root / "seen.json"
            seen_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "baseline_created_at": 1,
                        "fallback_baseline": {"completed_before": 0},
                        "seen_turns": {},
                    }
                ),
                encoding="utf-8",
            )

            write_session(codex_home, "00000000-0000-4000-8000-000000000001", "run", "", "", now - 4)
            write_session(codex_home, "00000000-0000-4000-8000-000000000002", "review", "task_complete", "t-review", now - 3)
            write_session(codex_home, "00000000-0000-4000-8000-000000000003", "failed", "task_failed", "t-failed", now - 2)
            write_session(codex_home, "00000000-0000-4000-8000-000000000004", "waiting", "request_user_input", "t-wait", now - 1)

            state = CodexSource(codex_home=codex_home, seen_path=seen_path).snapshot(limit=3)

            self.assertEqual(state.mode, "waiting")
            self.assertEqual(state.counts, {"waiting": 1, "failed": 1, "review": 1, "running": 1})
            self.assertEqual([item.state for item in state.bubbles], ["waiting", "failed", "review"])


if __name__ == "__main__":
    unittest.main()
