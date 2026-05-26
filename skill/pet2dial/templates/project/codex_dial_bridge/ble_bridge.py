from __future__ import annotations

import asyncio
import itertools
from collections.abc import Callable

from .open_thread import open_thread
from .protocol import EVENT_CHAR_UUID, SERVICE_UUID, STATE_CHAR_UUID, DialState, encode_state, frame_payload, parse_event, visual_signature
from .seen_state import mark_seen


class BleUnavailable(RuntimeError):
    pass


class DialBleBridge:
    def __init__(self, device_name: str = "CodexDial", chunk_size: int = 160):
        self.device_name = device_name
        self.chunk_size = chunk_size
        self._seq = itertools.count(1)
        self._thread_states: dict[str, str] = {}
        self._pending_seen: set[str] = set()

    async def _load_bleak(self):
        try:
            from bleak import BleakClient, BleakScanner
        except ImportError as exc:
            raise BleUnavailable("Install BLE support with: pip install -r requirements.txt") from exc
        return BleakClient, BleakScanner

    async def connect_and_run(self, state_provider: Callable[[], DialState], interval: float = 2.0) -> None:
        while True:
            try:
                await self._connect_once(state_provider, interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"BLE bridge stopped: {exc}. Reconnecting in 3s...", flush=True)
                await asyncio.sleep(3.0)

    async def _connect_once(self, state_provider: Callable[[], DialState], interval: float) -> None:
        BleakClient, BleakScanner = await self._load_bleak()
        print(f"Scanning for {self.device_name}...", flush=True)
        device = await BleakScanner.find_device_by_filter(
            lambda dev, adv: dev.name == self.device_name or SERVICE_UUID.lower() in [u.lower() for u in adv.service_uuids],
            timeout=15.0,
        )
        if device is None:
            raise RuntimeError(f"Could not find BLE device named {self.device_name!r}")

        print(f"Connecting to {device.name or device.address}...", flush=True)
        async with BleakClient(device) as client:
            await client.start_notify(EVENT_CHAR_UUID, self._handle_event)
            print("Connected. Syncing Codex state. Press Ctrl+C to stop.", flush=True)
            last_summary = ""
            last_visual = None
            while True:
                state = state_provider()
                self._thread_states = {item.thread_id: item.state for item in state.bubbles if item.thread_id}
                summary = f"pet={state.pet} mode={state.mode} bubbles=" + ",".join(item.state for item in state.bubbles[:8])
                if summary != last_summary:
                    print(f"Sync {summary}", flush=True)
                    last_summary = summary
                visual = visual_signature(state)
                if visual != last_visual:
                    await self.write_state(client, state)
                    last_visual = visual
                await asyncio.sleep(interval)

    async def write_state(self, client, state: DialState) -> None:
        payload = encode_state(state)
        seq = next(self._seq)
        for frame in frame_payload(payload, seq, self.chunk_size):
            await client.write_gatt_char(STATE_CHAR_UUID, frame, response=True)
            await asyncio.sleep(0.015)

    def _handle_event(self, _sender, data: bytearray) -> None:
        kind, value = parse_event(bytes(data))
        if kind == "CLICK" and value:
            print(f"Opening Codex thread {value}", flush=True)
            if self._thread_states.get(value) in {"done", "review"}:
                self._pending_seen.add(value)
            open_thread(value)
        elif kind == "LEAVE" and value:
            if value in self._pending_seen:
                self._pending_seen.remove(value)
                print(f"Marking reviewed Codex thread {value}", flush=True)
                mark_seen(value)
        else:
            print(f"Dial event: {kind} {value}".strip(), flush=True)
