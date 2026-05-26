#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_PROJECT = Path.home() / "CodexDialPet"
DEFAULT_CODEX_HOME = Path.home() / ".codex"
ROWS = "0,1,2,3,4,5,6,7,8"


def skill_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def template_dir() -> Path:
    return skill_dir() / "templates" / "project"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def status(label: str, ok: bool, detail: str) -> bool:
    marker = "OK" if ok else "NEED"
    print(f"[{marker}] {label}: {detail}")
    return ok


def selected_pet(codex_home: Path = DEFAULT_CODEX_HOME) -> str:
    state_path = codex_home / ".codex-global-state.json"
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return newest_pet(codex_home)
    persisted = data.get("electron-persisted-atom-state")
    if isinstance(persisted, dict):
        avatar_ids = persisted.get("first-awake-pet-notification-avatar-ids")
        if isinstance(avatar_ids, list):
            for value in reversed(avatar_ids):
                if isinstance(value, str) and value.startswith("custom:"):
                    pet_id = value.split(":", 1)[1]
                    if pet_exists(codex_home, pet_id):
                        return pet_id
    return newest_pet(codex_home)


def newest_pet(codex_home: Path = DEFAULT_CODEX_HOME) -> str:
    pets_dir = codex_home / "pets"
    candidates: list[tuple[float, str]] = []
    if pets_dir.exists():
        for manifest in pets_dir.glob("*/pet.json"):
            spritesheet = manifest.parent / "spritesheet.webp"
            if spritesheet.exists():
                candidates.append((max(manifest.stat().st_mtime, spritesheet.stat().st_mtime), manifest.parent.name))
    if not candidates:
        return ""
    return sorted(candidates, reverse=True)[0][1]


def pet_exists(codex_home: Path, pet_id: str) -> bool:
    pet_dir = codex_home / "pets" / pet_id
    return (pet_dir / "pet.json").exists() and (pet_dir / "spritesheet.webp").exists()


def project_python(project: Path) -> Path:
    return project / ".venv" / "bin" / "python"


def project_pio(project: Path) -> Path | str:
    local = project / ".venv" / "bin" / "pio"
    if local.exists():
        return local
    found = shutil.which("pio") or shutil.which("platformio")
    if found:
        return found
    return local


def doctor(args: argparse.Namespace) -> int:
    ok = True
    codex_home = args.codex_home
    pet_id = selected_pet(codex_home)
    ok &= status("macOS", platform.system() == "Darwin", platform.platform())
    ok &= status("Python", sys.version_info >= (3, 10), sys.version.split()[0])
    ok &= status("Codex home", codex_home.exists(), str(codex_home))
    ok &= status("Codex sessions", (codex_home / "sessions").exists(), str(codex_home / "sessions"))
    ok &= status("selected pet", bool(pet_id), pet_id or "no Codex custom pet found")
    if pet_id:
        ok &= status("pet package", pet_exists(codex_home, pet_id), str(codex_home / "pets" / pet_id))
    ports = sorted(Path("/dev").glob("cu.usbmodem*"))
    status("Dial USB serial", bool(ports), ", ".join(str(Path("/dev") / item.name) for item in ports) or "plug Dial into USB for flashing")
    project = args.project
    if project.exists():
        status("project", True, str(project))
        status("project venv", project_python(project).exists(), str(project_python(project)))
        status("PlatformIO", Path(project_pio(project)).exists() if isinstance(project_pio(project), Path) else True, str(project_pio(project)))
    else:
        status("project", False, f"{project} has not been initialized")
    return 0 if ok else 1


def init_project(args: argparse.Namespace) -> int:
    project = args.project
    if project.exists() and any(project.iterdir()) and not args.force:
        raise SystemExit(f"Project exists and is not empty: {project}. Use --force to refresh template files.")
    project.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template_dir(), project, dirs_exist_ok=True)
    (project / "state").mkdir(exist_ok=True)
    (project / "logs").mkdir(exist_ok=True)
    print(f"Initialized pet2dial project: {project}")
    return 0


def setup_env(args: argparse.Namespace) -> int:
    project = args.project
    if not (project / "requirements.txt").exists():
        raise SystemExit(f"Missing project template. Run init first: {project}")
    if not project_python(project).exists():
        run([sys.executable, "-m", "venv", str(project / ".venv")])
    python = str(project_python(project))
    run([python, "-m", "pip", "install", "--upgrade", "pip"])
    run([python, "-m", "pip", "install", "-r", str(project / "requirements.txt"), "platformio==6.1.19"])
    return 0


def convert(args: argparse.Namespace) -> int:
    project = args.project
    pet_id = args.pet or selected_pet(args.codex_home)
    if not pet_id:
        raise SystemExit("No Codex pet found. Create or select a custom pet in Codex first.")
    if not pet_exists(args.codex_home, pet_id):
        raise SystemExit(f"Missing Codex pet package: {args.codex_home / 'pets' / pet_id}")
    python = str(project_python(project) if project_python(project).exists() else Path(sys.executable))
    out = project / "firmware" / "include" / "pet_frames.h"
    run(
        [
            python,
            str(project / "tools" / "convert_pet.py"),
            pet_id,
            "--out",
            str(out),
            "--size",
            str(args.size),
            "--frames",
            "8",
            "--rows",
            ROWS,
            "--codex-home",
            str(args.codex_home),
        ]
    )
    return 0


def build(args: argparse.Namespace) -> int:
    pio = str(project_pio(args.project))
    run([pio, "run", "-d", str(args.project / "firmware")])
    return 0


def first_dial_port() -> str:
    ports = sorted(Path("/dev").glob("cu.usbmodem*"))
    if not ports:
        raise SystemExit("No /dev/cu.usbmodem* device found. Plug the Dial into USB for firmware upload.")
    return str(Path("/dev") / ports[0].name)


def upload(args: argparse.Namespace) -> int:
    pio = str(project_pio(args.project))
    port = args.port or first_dial_port()
    run([pio, "run", "-d", str(args.project / "firmware"), "-t", "upload", "--upload-port", port])
    return 0


def run_bridge(args: argparse.Namespace) -> int:
    python = str(project_python(args.project) if project_python(args.project).exists() else Path(sys.executable))
    run(
        [
            python,
            "-m",
            "codex_dial_bridge.cli",
            "run",
            "--codex-home",
            str(args.codex_home),
            "--pet",
            args.pet or "auto",
            "--device-name",
            args.device_name,
            "--interval",
            str(args.interval),
        ],
        cwd=args.project,
    )
    return 0


def verify(args: argparse.Namespace) -> int:
    project = args.project
    checks = [
        ("firmware header", project / "firmware" / "include" / "pet_frames.h"),
        ("firmware binary", project / "firmware" / ".pio" / "build" / "m5dial" / "firmware.bin"),
        ("bridge package", project / "codex_dial_bridge" / "cli.py"),
    ]
    ok = True
    for label, path in checks:
        ok &= status(label, path.exists(), str(path))
    python = str(project_python(project) if project_python(project).exists() else Path(sys.executable))
    if (project / "codex_dial_bridge").exists():
        run([python, "-m", "codex_dial_bridge.cli", "snapshot", "--codex-home", str(args.codex_home), "--pet", args.pet or "auto"], cwd=project)
    return 0 if ok else 1


def success_path(args: argparse.Namespace) -> int:
    init_project(args)
    setup_env(args)
    convert(args)
    build(args)
    if args.upload:
        upload(args)
    verify(args)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare, flash, and run the Codex pet-to-M5Stack Dial path.")
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor")
    init = sub.add_parser("init")
    init.add_argument("--force", action="store_true")
    sub.add_parser("setup-env")

    convert_cmd = sub.add_parser("convert")
    convert_cmd.add_argument("--pet")
    convert_cmd.add_argument("--size", type=int, default=96)

    sub.add_parser("build")
    upload_cmd = sub.add_parser("upload")
    upload_cmd.add_argument("--port")

    bridge = sub.add_parser("run-bridge")
    bridge.add_argument("--pet")
    bridge.add_argument("--device-name", default="CodexDial")
    bridge.add_argument("--interval", type=float, default=2.0)

    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("--pet")

    all_cmd = sub.add_parser("success-path")
    all_cmd.add_argument("--force", action="store_true")
    all_cmd.add_argument("--pet")
    all_cmd.add_argument("--size", type=int, default=96)
    all_cmd.add_argument("--upload", action="store_true")
    all_cmd.add_argument("--port")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return doctor(args)
    if args.command == "init":
        return init_project(args)
    if args.command == "setup-env":
        return setup_env(args)
    if args.command == "convert":
        return convert(args)
    if args.command == "build":
        return build(args)
    if args.command == "upload":
        return upload(args)
    if args.command == "run-bridge":
        return run_bridge(args)
    if args.command == "verify":
        return verify(args)
    if args.command == "success-path":
        return success_path(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
