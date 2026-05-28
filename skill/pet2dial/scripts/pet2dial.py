#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_PROJECT = Path.home() / "CodexDialPet"
DEFAULT_CODEX_HOME = Path.home() / ".codex"
ROWS = "0,1,2,3,4,5,6,7,8"
LAUNCH_AGENT_LABEL = "local.codex.dial.bridge"
PLATFORMIO_VERSION = "platformio==6.1.19"
REQUIRED_MODULES = {
    "bleak": "bleak",
    "PIL": "Pillow",
    "platformio": PLATFORMIO_VERSION,
}


def skill_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def template_dir() -> Path:
    return skill_dir() / "templates" / "project"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def run_capture(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=False, text=True, capture_output=True)


def explain_failure(action: str, exc: subprocess.CalledProcessError) -> int:
    print(f"[FAIL] {action} failed with exit code {exc.returncode}.")
    if exc.cmd:
        print("Command: " + " ".join(str(part) for part in exc.cmd))
    print("Next steps:")
    print("- Run `python3 scripts/pet2dial.py doctor` for a full environment check.")
    print("- If this is a BLE bridge failure on macOS, run `python3 scripts/pet2dial.py logs` and check Bluetooth permission prompts.")
    print("- If this is a firmware upload failure, confirm the Dial is connected over USB and appears as /dev/cu.usbmodem*.")
    return exc.returncode or 1


def status(label: str, ok: bool, detail: str) -> bool:
    marker = "OK" if ok else "NEED"
    print(f"[{marker}] {label}: {detail}")
    return ok


def selected_pet(codex_home: Path = DEFAULT_CODEX_HOME) -> str:
    config_path = codex_home / "config.toml"
    try:
        config_text = config_path.read_text(encoding="utf-8")
    except OSError:
        config_text = ""
    match = re.search(r'(?m)^\s*selected-avatar-id\s*=\s*"custom:([^"]+)"', config_text)
    if match and pet_exists(codex_home, match.group(1)):
        return match.group(1)

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
    project = args.project
    ok &= status("macOS", platform.system() == "Darwin", platform.platform())
    ok &= status("Python", sys.version_info >= (3, 10), sys.version.split()[0])
    ok &= status("Codex home", codex_home.exists(), str(codex_home))
    ok &= status("Codex sessions", (codex_home / "sessions").exists(), str(codex_home / "sessions"))
    ok &= status("selected pet", bool(pet_id), pet_id or "no Codex custom pet found")
    if pet_id:
        ok &= status("pet package", pet_exists(codex_home, pet_id), str(codex_home / "pets" / pet_id))
    ports = sorted(Path("/dev").glob("cu.usbmodem*"))
    status("Dial USB serial", bool(ports), ", ".join(str(Path("/dev") / item.name) for item in ports) or "plug Dial into USB for flashing")
    if project.exists():
        ok &= status("project", project_ready(project), str(project) if project_ready(project) else f"{project} is missing template files")
        venv_python = project_python(project)
        ok &= status("project venv", venv_python.exists(), str(venv_python))
        if venv_python.exists():
            missing = missing_modules(venv_python)
            ok &= status("bridge dependencies", not missing, "installed" if not missing else "missing " + ", ".join(missing))
        ok &= status("PlatformIO", Path(project_pio(project)).exists() if isinstance(project_pio(project), Path) else True, str(project_pio(project)))
        status("bridge app", bridge_app_path(project).exists(), str(bridge_app_path(project)))
        log = bridge_log_path(project)
        if log.exists():
            lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
            connected = any("Connected. Syncing Codex state." in line for line in lines)
            sync_lines = [line for line in lines if line.startswith("Sync ")]
            status("recent bridge connection", connected, "connected" if connected else "no recent connection in last 80 log lines")
            status("recent bridge sync", bool(sync_lines), sync_lines[-1] if sync_lines else "no recent Sync line")
        else:
            status("bridge log", False, str(log))
    else:
        status("project", False, f"{project} has not been initialized")
    agent = launch_agent_path()
    agent_loaded = run_capture(["launchctl", "print", f"gui/{os.getuid()}/{LAUNCH_AGENT_LABEL}"]).returncode == 0
    status("LaunchAgent installed", agent.exists(), str(agent))
    status("LaunchAgent running", agent_loaded, LAUNCH_AGENT_LABEL if agent_loaded else "not loaded")
    return 0 if ok else 1


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def codex_app_info() -> dict[str, str | bool]:
    app = Path("/Applications/Codex.app")
    info_path = app / "Contents" / "Info.plist"
    asar_path = app / "Contents" / "Resources" / "app.asar"
    result: dict[str, str | bool] = {
        "path": str(app),
        "exists": app.exists(),
        "version": "",
        "build": "",
        "app_asar_sha256": "",
    }
    if info_path.exists():
        try:
            with info_path.open("rb") as handle:
                info = plistlib.load(handle)
            result["version"] = str(info.get("CFBundleShortVersionString", ""))
            result["build"] = str(info.get("CFBundleVersion", ""))
        except (OSError, plistlib.InvalidFileException):
            pass
    if asar_path.exists():
        result["app_asar_sha256"] = file_sha256(asar_path)
    return result


def pet_atlas_info(codex_home: Path, pet_id: str) -> dict[str, int | str | bool]:
    spritesheet = codex_home / "pets" / pet_id / "spritesheet.webp"
    result: dict[str, int | str | bool] = {
        "path": str(spritesheet),
        "exists": spritesheet.exists(),
        "width": 0,
        "height": 0,
        "columns": 0,
        "rows": 0,
        "expected_geometry": False,
    }
    if not spritesheet.exists():
        return result
    try:
        from PIL import Image
    except ImportError:
        sips = shutil.which("sips")
        if not sips:
            result["error"] = "Pillow is not installed and macOS sips was not found; run setup-env for atlas dimension checks."
            return result
        probe = run_capture([sips, "-g", "pixelWidth", "-g", "pixelHeight", str(spritesheet)])
        if probe.returncode != 0:
            result["error"] = probe.stderr.strip() or "sips could not read the pet atlas."
            return result
        width_match = re.search(r"pixelWidth:\s*(\d+)", probe.stdout)
        height_match = re.search(r"pixelHeight:\s*(\d+)", probe.stdout)
        if not width_match or not height_match:
            result["error"] = "sips output did not include pixel dimensions."
            return result
        width = int(width_match.group(1))
        height = int(height_match.group(1))
        result["width"] = width
        result["height"] = height
        result["columns"] = width // 192 if width % 192 == 0 else 0
        result["rows"] = height // 208 if height % 208 == 0 else 0
        result["expected_geometry"] = width == 1536 and height == 1872
        return result
    try:
        with Image.open(spritesheet) as image:
            width, height = image.size
    except OSError as exc:
        result["error"] = str(exc)
        return result
    result["width"] = width
    result["height"] = height
    result["columns"] = width // 192 if width % 192 == 0 else 0
    result["rows"] = height // 208 if height % 208 == 0 else 0
    result["expected_geometry"] = width == 1536 and height == 1872
    return result


def recent_rollout_events(codex_home: Path, limit_files: int = 40) -> list[str]:
    sessions = codex_home / "sessions"
    if not sessions.exists():
        return []
    files = sorted(sessions.glob("*/*/*/rollout-*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit_files]
    event_types: set[str] = set()
    for path in files:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    payload = event.get("payload")
                    if not isinstance(payload, dict):
                        continue
                    event_type = payload.get("type")
                    if isinstance(event_type, str):
                        event_types.add(event_type)
                    nested = payload.get("payload")
                    if isinstance(nested, dict):
                        nested_type = nested.get("type")
                        if isinstance(nested_type, str):
                            event_types.add(nested_type)
        except OSError:
            continue
    return sorted(event_types)


def diff_snapshot(previous: dict[str, object], current: dict[str, object]) -> list[str]:
    changes: list[str] = []
    checks = [
        ("codex_app.version", previous.get("codex_app", {}), current.get("codex_app", {}), "version"),
        ("codex_app.build", previous.get("codex_app", {}), current.get("codex_app", {}), "build"),
        ("codex_app.app_asar_sha256", previous.get("codex_app", {}), current.get("codex_app", {}), "app_asar_sha256"),
        ("selected_pet_id", previous, current, "selected_pet_id"),
    ]
    for label, old_parent, new_parent, key in checks:
        old_value = old_parent.get(key) if isinstance(old_parent, dict) else None
        new_value = new_parent.get(key) if isinstance(new_parent, dict) else None
        if old_value != new_value:
            changes.append(f"{label}: {old_value or '<empty>'} -> {new_value or '<empty>'}")
    old_atlas = previous.get("pet_atlas", {})
    new_atlas = current.get("pet_atlas", {})
    for key in ("width", "height", "rows", "columns", "expected_geometry"):
        old_value = old_atlas.get(key) if isinstance(old_atlas, dict) else None
        new_value = new_atlas.get(key) if isinstance(new_atlas, dict) else None
        if old_value != new_value:
            changes.append(f"pet_atlas.{key}: {old_value} -> {new_value}")
    return changes


def codex_compat(args: argparse.Namespace) -> int:
    ensure_project(args)
    codex_home = args.codex_home
    pet_id = selected_pet(codex_home)
    snapshot = {
        "schema": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "codex_home": str(codex_home),
        "codex_home_exists": codex_home.exists(),
        "codex_sessions_exists": (codex_home / "sessions").exists(),
        "codex_app": codex_app_info(),
        "selected_pet_id": pet_id,
        "pet_package_exists": pet_exists(codex_home, pet_id) if pet_id else False,
        "pet_atlas": pet_atlas_info(codex_home, pet_id) if pet_id else {},
        "detected_rollout_events": recent_rollout_events(codex_home),
        "wire_contract": {
            "states": ["idle", "waiting", "failed", "review", "running"],
            "task_card_states": ["waiting", "failed", "review", "running"],
            "priority": ["waiting", "failed", "review", "running", "idle"],
            "events": ["CLICK|<thread_id>", "LEAVE|<thread_id>"],
        },
    }
    state_dir = args.project / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = state_dir / "codex_compat_snapshot.json"
    previous: dict[str, object] | None = None
    if snapshot_path.exists():
        try:
            previous = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = None
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ok = True
    ok &= status("macOS baseline", platform.system() == "Darwin", platform.platform())
    ok &= status("Codex home", codex_home.exists(), str(codex_home))
    ok &= status("Codex sessions", (codex_home / "sessions").exists(), str(codex_home / "sessions"))
    ok &= status("selected pet", bool(pet_id), pet_id or "no custom pet found")
    if pet_id:
        ok &= status("pet package", bool(snapshot["pet_package_exists"]), str(codex_home / "pets" / pet_id))
        atlas = snapshot["pet_atlas"]
        if isinstance(atlas, dict):
            detail = f"{atlas.get('width', 0)}x{atlas.get('height', 0)} rows={atlas.get('rows', 0)} columns={atlas.get('columns', 0)}"
            ok &= status("pet atlas geometry", bool(atlas.get("expected_geometry")), detail)
            if atlas.get("error"):
                print(f"[WARN] atlas check: {atlas['error']}")
    app_info = snapshot["codex_app"]
    if isinstance(app_info, dict):
        status("Codex.app", bool(app_info.get("exists")), str(app_info.get("path", "")))
        if app_info.get("version") or app_info.get("build"):
            print(f"[INFO] Codex version: {app_info.get('version') or '<unknown>'} build {app_info.get('build') or '<unknown>'}")
        if app_info.get("app_asar_sha256"):
            print(f"[INFO] app.asar sha256: {str(app_info['app_asar_sha256'])[:16]}...")
    events = snapshot["detected_rollout_events"]
    print("[INFO] Detected rollout event types: " + (", ".join(events[:24]) if isinstance(events, list) and events else "<none>"))
    if previous:
        changes = diff_snapshot(previous, snapshot)
        if changes:
            print("[WARN] Codex compatibility snapshot changed since last run:")
            for change in changes:
                print(f"- {change}")
        else:
            print("[OK] Snapshot unchanged since last run")
    else:
        print("[OK] Wrote first compatibility snapshot")
    print(f"[OK] Snapshot: {snapshot_path}")
    print("Reference: skill/pet2dial/references/codex-compatibility.md")
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


def project_ready(project: Path) -> bool:
    required = [
        project / "requirements.txt",
        project / "codex_dial_bridge" / "cli.py",
        project / "tools" / "convert_pet.py",
        project / "firmware" / "platformio.ini",
    ]
    return all(path.exists() for path in required)


def ensure_project(args: argparse.Namespace) -> None:
    if project_ready(args.project):
        return
    print(f"[SETUP] Initializing project at {args.project}")
    init_args = argparse.Namespace(project=args.project, force=False)
    init_project(init_args)


def missing_modules(python: Path) -> list[str]:
    missing: list[str] = []
    for module, package in REQUIRED_MODULES.items():
        result = run_capture([str(python), "-c", f"import {module}"])
        if result.returncode != 0:
            missing.append(package)
    return missing


def ensure_env(args: argparse.Namespace, include_pio: bool = False) -> None:
    ensure_project(args)
    project = args.project
    python = project_python(project)
    if not python.exists():
        print(f"[SETUP] Creating isolated Python environment: {project / '.venv'}")
        run([sys.executable, "-m", "venv", str(project / ".venv")])
    required = missing_modules(python)
    if not include_pio:
        required = [item for item in required if not item.startswith("platformio")]
    if required:
        print("[SETUP] Installing missing bridge dependencies into the project venv: " + ", ".join(required))
        run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
        run([str(python), "-m", "pip", "install", "-r", str(project / "requirements.txt")])
        if include_pio and any(item.startswith("platformio") for item in required):
            run([str(python), "-m", "pip", "install", PLATFORMIO_VERSION])


def bridge_app_path(project: Path) -> Path:
    return project / "macos" / "CodexDialBridge.app"


def bridge_log_path(project: Path) -> Path:
    return project / "logs" / "bridge.log"


def launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def resolve_bridge_pet(args: argparse.Namespace) -> str:
    return args.pet or "auto"


def create_bridge_app(args: argparse.Namespace) -> Path:
    project = args.project
    app = bridge_app_path(project)
    macos = app / "Contents" / "MacOS"
    macos.mkdir(parents=True, exist_ok=True)
    (app / "Contents" / "Resources").mkdir(parents=True, exist_ok=True)
    (project / "logs").mkdir(exist_ok=True)

    info = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleDisplayName": "CodexDialBridge",
        "CFBundleExecutable": "CodexDialBridge",
        "CFBundleIdentifier": LAUNCH_AGENT_LABEL,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "CodexDialBridge",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "13.0",
        "LSUIElement": True,
        "NSBluetoothAlwaysUsageDescription": "CodexDialBridge uses Bluetooth to sync the selected Codex pet and task state to the M5Stack Dial.",
    }
    with (app / "Contents" / "Info.plist").open("wb") as handle:
        plistlib.dump(info, handle)

    executable = macos / "CodexDialBridge"
    script = f"""#!/bin/zsh
set -u

PROJECT={str(project)!r}
LOG_DIR="$PROJECT/logs"
LOG_FILE="$LOG_DIR/bridge.log"

mkdir -p "$LOG_DIR"
cd "$PROJECT" || exit 1

{{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting CodexDialBridge"
  exec "$PROJECT/.venv/bin/python" -m codex_dial_bridge.cli run \\
    --codex-home {str(args.codex_home)!r} \\
    --pet {resolve_bridge_pet(args)!r} \\
    --device-name {args.device_name!r} \\
    --interval {str(args.interval)!r}
}} >> "$LOG_FILE" 2>&1
"""
    executable.write_text(script, encoding="utf-8")
    executable.chmod(0o755)

    codesign = shutil.which("codesign")
    if codesign:
        subprocess.run([codesign, "--force", "--deep", "--sign", "-", str(app)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return app


def convert(args: argparse.Namespace) -> int:
    ensure_project(args)
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
    ensure_env(args, include_pio=True)
    pio = str(project_pio(args.project))
    run([pio, "run", "-d", str(args.project / "firmware")])
    return 0


def first_dial_port() -> str:
    ports = sorted(Path("/dev").glob("cu.usbmodem*"))
    if not ports:
        raise SystemExit("No /dev/cu.usbmodem* device found. Plug the Dial into USB for firmware upload.")
    return str(Path("/dev") / ports[0].name)


def upload(args: argparse.Namespace) -> int:
    ensure_env(args, include_pio=True)
    pio = str(project_pio(args.project))
    port = args.port or first_dial_port()
    run([pio, "run", "-d", str(args.project / "firmware"), "-t", "upload", "--upload-port", port])
    return 0


def run_bridge(args: argparse.Namespace) -> int:
    try:
        ensure_project(args)
        if args.global_python:
            python = Path(sys.executable)
            run(
                [
                    str(python),
                    "-m",
                    "codex_dial_bridge.cli",
                    "run",
                    "--codex-home",
                    str(args.codex_home),
                    "--pet",
                    resolve_bridge_pet(args),
                    "--device-name",
                    args.device_name,
                    "--interval",
                    str(args.interval),
                ],
                cwd=args.project,
            )
        else:
            ensure_env(args)
            app = create_bridge_app(args)
            print(f"[OK] Starting bridge app: {app}")
            print(f"[OK] Logs: {bridge_log_path(args.project)}")
            run(["/usr/bin/open", "-W", "-g", str(app)])
    except subprocess.CalledProcessError as exc:
        return explain_failure("BLE bridge", exc)
    return 0


def install_autostart(args: argparse.Namespace) -> int:
    ensure_env(args)
    app = create_bridge_app(args)
    plist_path = launch_agent_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": ["/usr/bin/open", "-W", "-g", str(app)],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(args.project / "logs" / "launchagent.out.log"),
        "StandardErrorPath": str(args.project / "logs" / "launchagent.err.log"),
        "WorkingDirectory": str(args.project),
    }
    with plist_path.open("wb") as handle:
        plistlib.dump(plist, handle)
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(plist_path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    result = subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist_path)], check=False)
    if result.returncode != 0:
        print(f"[FAIL] Could not install LaunchAgent: {plist_path}")
        print("Next step: run `launchctl print gui/$UID/local.codex.dial.bridge` for macOS launchd details.")
        return result.returncode
    subprocess.run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{LAUNCH_AGENT_LABEL}"], check=False)
    print(f"[OK] Installed login autostart: {plist_path}")
    print(f"[OK] Bridge app: {app}")
    return 0


def uninstall_autostart(args: argparse.Namespace) -> int:
    plist_path = launch_agent_path()
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(plist_path)], check=False)
    if plist_path.exists():
        plist_path.unlink()
    print(f"[OK] Removed login autostart: {plist_path}")
    return 0


def service_status(args: argparse.Namespace) -> int:
    print(f"Project: {args.project}")
    print(f"Bridge app: {bridge_app_path(args.project)}")
    print(f"LaunchAgent: {launch_agent_path()}")
    result = run_capture(["launchctl", "print", f"gui/{os.getuid()}/{LAUNCH_AGENT_LABEL}"])
    if result.returncode == 0:
        print("[OK] LaunchAgent loaded")
        for line in result.stdout.splitlines():
            if any(key in line for key in ("state =", "pid =", "last exit code =", "runs =")):
                print(line.strip())
    else:
        print("[NEED] LaunchAgent not loaded")
    log = bridge_log_path(args.project)
    if log.exists():
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
        connected = any("Connected. Syncing Codex state." in line for line in lines)
        sync = [line for line in lines if line.startswith("Sync ")]
        status("recent BLE connection", connected, "connected" if connected else "no recent connection in last 40 log lines")
        if sync:
            print("Last sync: " + sync[-1])
    else:
        status("bridge log", False, str(log))
    return 0


def restart_bridge(args: argparse.Namespace) -> int:
    if not launch_agent_path().exists():
        print("[NEED] LaunchAgent is not installed. Run `python3 scripts/pet2dial.py install-autostart` first.")
        return 1
    result = subprocess.run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{LAUNCH_AGENT_LABEL}"], check=False)
    if result.returncode == 0:
        print("[OK] Restarted CodexDial bridge service")
    return result.returncode


def show_logs(args: argparse.Namespace) -> int:
    log = bridge_log_path(args.project)
    if not log.exists():
        print(f"[NEED] No bridge log found: {log}")
        print("Next step: run `python3 scripts/pet2dial.py run-bridge` or `python3 scripts/pet2dial.py install-autostart`.")
        return 1
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines[-args.lines :]:
        print(line)
    return 0


def clear_review_backlog(args: argparse.Namespace) -> int:
    ensure_env(args)
    run(
        [
            str(project_python(args.project)),
            "-m",
            "codex_dial_bridge.cli",
            "clear-review-backlog",
            "--codex-home",
            str(args.codex_home),
            "--pet",
            args.pet or "auto",
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
    sub.add_parser("codex-compat")
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
    bridge.add_argument("--global-python", action="store_true")

    autostart = sub.add_parser("install-autostart")
    autostart.add_argument("--pet")
    autostart.add_argument("--device-name", default="CodexDial")
    autostart.add_argument("--interval", type=float, default=2.0)

    sub.add_parser("uninstall-autostart")
    sub.add_parser("status")
    sub.add_parser("restart-bridge")

    logs = sub.add_parser("logs")
    logs.add_argument("--lines", type=int, default=80)

    clear_reviews = sub.add_parser("clear-review-backlog")
    clear_reviews.add_argument("--pet")

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
    if args.command == "codex-compat":
        return codex_compat(args)
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
    if args.command == "install-autostart":
        return install_autostart(args)
    if args.command == "uninstall-autostart":
        return uninstall_autostart(args)
    if args.command == "status":
        return service_status(args)
    if args.command == "restart-bridge":
        return restart_bridge(args)
    if args.command == "logs":
        return show_logs(args)
    if args.command == "clear-review-backlog":
        return clear_review_backlog(args)
    if args.command == "verify":
        return verify(args)
    if args.command == "success-path":
        return success_path(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
