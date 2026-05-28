from __future__ import annotations

import re
import subprocess


THREAD_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def validate_thread_id(thread_id: str) -> str:
    value = thread_id.strip()
    if not THREAD_RE.fullmatch(value):
        raise ValueError(f"invalid Codex thread id: {thread_id!r}")
    return value


def thread_url(thread_id: str) -> str:
    return f"codex://threads/{validate_thread_id(thread_id)}"


def open_thread(thread_id: str) -> None:
    url = thread_url(thread_id)
    result = subprocess.run(["/usr/bin/open", url], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        print(f"Failed to open Codex thread {thread_id}: open exited {result.returncode} {message}".strip(), flush=True)
    else:
        print(f"Opened Codex URL {url}", flush=True)
