from __future__ import annotations

import argparse
import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .ble_bridge import DialBleBridge
from .codex_source import CodexSource
from .open_thread import open_thread
from .seen_state import mark_seen


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-dial", description="Mirror Codex pet state to M5Stack Dial.")
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser("snapshot", help="Print current Codex Dial state.")
    snapshot.add_argument("--codex-home", type=Path)
    snapshot.add_argument("--pet", default="auto")
    snapshot.add_argument("--pretty", action="store_true")

    run = sub.add_parser("run", help="Run BLE bridge.")
    run.add_argument("--codex-home", type=Path)
    run.add_argument("--pet", default="auto")
    run.add_argument("--device-name", default="CodexDial")
    run.add_argument("--interval", type=float, default=2.0)

    serve = sub.add_parser("serve-sim", help="Serve simulator JSON and click endpoints.")
    serve.add_argument("--codex-home", type=Path)
    serve.add_argument("--pet", default="auto")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    open_cmd = sub.add_parser("open-thread", help="Open a Codex thread by id.")
    open_cmd.add_argument("thread_id")

    clear_reviews = sub.add_parser("clear-review-backlog", help="Mark existing task_complete reviews as already seen.")
    clear_reviews.add_argument("--codex-home", type=Path)
    clear_reviews.add_argument("--pet", default="auto")
    return parser


def make_source(args) -> CodexSource:
    return CodexSource(codex_home=args.codex_home, pet=args.pet)


class SimHandler(BaseHTTPRequestHandler):
    source: CodexSource

    def _send_json(self, data: dict, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/state":
            self._send_json(self.source.snapshot().to_wire())
            return
        if parsed.path == "/open":
            query = parse_qs(parsed.query)
            thread_id = query.get("thread_id", [""])[0]
            turn_id = query.get("turn_id", [""])[0]
            try:
                mark_seen(thread_id, turn_id)
                open_thread(thread_id)
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
                return
            self._send_json({"ok": True, "thread_id": thread_id})
            return
        self._send_json({"ok": False, "error": "not found"}, status=404)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[sim] {self.address_string()} {fmt % args}")


def serve_sim(source: CodexSource, host: str, port: int) -> None:
    handler = type("BoundSimHandler", (SimHandler,), {"source": source})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Simulator state server: http://{host}:{port}/state")
    print("Open simulator/index.html in a browser.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping simulator server.")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "snapshot":
        state = make_source(args).snapshot().to_wire()
        print(json.dumps(state, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0
    if args.command == "run":
        source = make_source(args)
        bridge = DialBleBridge(device_name=args.device_name)
        asyncio.run(bridge.connect_and_run(source.snapshot, interval=args.interval))
        return 0
    if args.command == "serve-sim":
        serve_sim(make_source(args), args.host, args.port)
        return 0
    if args.command == "open-thread":
        mark_seen(args.thread_id)
        open_thread(args.thread_id)
        return 0
    if args.command == "clear-review-backlog":
        added = make_source(args).mark_current_reviews_seen()
        print(f"Marked {added} existing task_complete review thread(s) as seen.")
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
