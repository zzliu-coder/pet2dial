from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Iterable


SERVICE_UUID = "c0de0001-d1a1-4f6f-9b7c-5e55c0de0001"
STATE_CHAR_UUID = "c0de0002-d1a1-4f6f-9b7c-5e55c0de0002"
EVENT_CHAR_UUID = "c0de0003-d1a1-4f6f-9b7c-5e55c0de0003"

MAX_BUBBLES = 8
DEFAULT_CHUNK_SIZE = 160


@dataclass(slots=True)
class Bubble:
    thread_id: str
    title: str
    state: str
    updated_at: float
    cwd: str = ""
    turn_id: str = ""


@dataclass(slots=True)
class DialState:
    v: int = 1
    pet: str = ""
    mode: str = "idle"
    now: float = 0.0
    bubbles: list[Bubble] = field(default_factory=list)

    def to_wire(self) -> dict:
        data = asdict(self)
        data["bubbles"] = [asdict(item) for item in self.bubbles[:MAX_BUBBLES]]
        return data


def compact_json(data: dict) -> str:
    # ASCII keeps BLE chunks byte-stable and avoids splitting UTF-8 code points.
    return json.dumps(data, ensure_ascii=True, separators=(",", ":"))


def encode_state(state: DialState) -> bytes:
    return compact_json(state.to_wire()).encode("utf-8")


def visual_signature(state: DialState) -> tuple:
    return (
        state.pet,
        state.mode,
        tuple((item.thread_id, item.turn_id, item.title, item.state) for item in state.bubbles[:MAX_BUBBLES]),
    )


def frame_payload(payload: bytes, seq: int, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[bytes]:
    if chunk_size < 32:
        raise ValueError("chunk_size must be at least 32")
    text = payload.decode("utf-8")
    parts = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)] or [""]
    total = len(parts)
    return [f"CD1|{seq}|{idx}|{total}|{part}".encode("utf-8") for idx, part in enumerate(parts)]


def parse_event(data: bytes | str) -> tuple[str, str]:
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    text = text.strip()
    if "|" not in text:
        return text, ""
    kind, value = text.split("|", 1)
    return kind, value


def decode_framed_payload(frames: Iterable[bytes | str]) -> dict:
    parts: dict[int, str] = {}
    expected_total: int | None = None
    seq: str | None = None
    for frame in frames:
        text = frame.decode("utf-8", errors="replace") if isinstance(frame, bytes) else frame
        prefix = text.split("|", 4)
        if len(prefix) != 5 or prefix[0] != "CD1":
            raise ValueError(f"invalid frame: {text[:40]!r}")
        _, frame_seq, idx_text, total_text, payload = prefix
        if seq is None:
            seq = frame_seq
        if frame_seq != seq:
            raise ValueError("mixed frame sequence")
        idx = int(idx_text)
        total = int(total_text)
        if expected_total is None:
            expected_total = total
        if total != expected_total:
            raise ValueError("mixed frame totals")
        parts[idx] = payload
    if expected_total is None:
        raise ValueError("no frames")
    missing = [idx for idx in range(expected_total) if idx not in parts]
    if missing:
        raise ValueError(f"missing frame chunks: {missing}")
    return json.loads("".join(parts[idx] for idx in range(expected_total)))
