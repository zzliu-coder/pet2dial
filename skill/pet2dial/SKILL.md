---
name: pet2dial
description: Mirror the currently selected Codex custom pet and Codex waiting/failed/review/running task state onto an M5Stack Dial or T-Encoder Pro round display. Use when the user wants to prepare a Mac, convert the Codex pet atlas, flash device firmware, run the BLE bridge, and verify the Codex pet appears on the external display.
---

# Pet2Dial

## Purpose

Put the Codex desktop pet onto a small round hardware display using the proven path from this run: one selected Codex custom pet, converted from the official Codex pet atlas into a 96x96 RGB565 firmware resource, flashed into device firmware, then synchronized from macOS to the device over BLE.

This skill is a success-path workflow. Keep the main path direct: check environment, create the project, convert the pet, build, upload, install or restart the bridge service, verify.

Treat the BLE bridge as a user-facing device service. The user should not need to understand the generated project directory, virtual environment, Python dependencies, or a terminal that must stay open.

M5Stack Dial remains the default success path. T-Encoder Pro is absorbed into this same skill as a second board target because it uses the same Codex pet source, bridge, BLE name, wire protocol, task cards, CLICK/LEAVE semantics, and review seen-state model. Its differences are firmware-level hardware adaptation: display driver, touch, encoder, circular safe area, font, and layout.

## Success Contract

The successful result is:

- Device firmware is flashed and advertises `CodexDial`.
- The device displays the user's selected Codex custom pet with stable color and animation.
- The pet uses all official Codex atlas rows: `idle`, `running-right`, `running-left`, `waving`, `jumping`, `failed`, `waiting`, `running`, and `review`.
- The bridge syncs active `waiting`, `failed`, `review`, and `running` task cards, plus global state counts for the pet view.
- Clicking a device card opens `codex://threads/<thread_id>`.
- A review card remains visible after click and is marked seen only after the user leaves that card by rotating away or returning to the pet view.

Use the defaults unless the user explicitly asks otherwise:

- project directory: `~/CodexDialPet`
- Codex home: `~/.codex`
- one pet only: the currently selected Codex custom pet
- atlas: `~/.codex/pets/<pet-id>/spritesheet.webp`
- output frame size: `96x96`
- frames: `8`
- rows: `0,1,2,3,4,5,6,7,8`
- firmware target: M5Stack Dial / M5StampS3
- alternate firmware target: T-Encoder Pro, when the user explicitly asks for T-Encoder
- BLE name: `CodexDial`
- bridge runtime: isolated project venv plus macOS app wrapper and optional LaunchAgent

Pet selection rules:

- `auto` means the currently selected Codex custom pet when Codex exposes one, with newest local custom pet as fallback.
- The primary selected-pet source is `~/.codex/config.toml` `selected-avatar-id = "custom:<pet-id>"`; older first-awake UI history is only a fallback.
- `--pet <pet-id>` pins a specific local pet package such as `~/.codex/pets/<pet-id>`.
- Do not hard-code pet ids, user paths, or previous-run examples into open-source defaults.

## Required User Conditions

Proceed when:

- The user is on macOS.
- Codex Desktop has at least one custom pet under `~/.codex/pets`.
- The target device is available for USB flashing.
- The user accepts that BLE is used for daily sync after flashing; USB is only needed for firmware upload.

Stop and ask for the smallest missing fact when:

- No Codex custom pet exists.
- Multiple likely USB serial devices exist and the script cannot identify the target device.
- The user wants to support a different board, a different OS, multiple pets, or runtime pet streaming.

## Workflow

1. Read this skill's `references/success-contract.md` and `references/codex-compatibility.md`. If the target is T-Encoder Pro, also read `references/t-encoder-pro.md`.
2. Run the doctor check from the skill directory:

```bash
python3 scripts/pet2dial.py doctor
```

3. Create or refresh the portable project:

```bash
python3 scripts/pet2dial.py init --force
```

4. Install the project environment:

```bash
python3 scripts/pet2dial.py setup-env
```

5. Convert the selected Codex pet:

```bash
python3 scripts/pet2dial.py convert
```

6. Build the firmware:

```bash
python3 scripts/pet2dial.py build
```

7. Upload firmware while the Dial is connected over USB:

```bash
python3 scripts/pet2dial.py upload
```

8. Run the bridge:

```bash
python3 scripts/pet2dial.py run-bridge
```

9. For daily use, install the background service:

```bash
python3 scripts/pet2dial.py install-autostart
```

10. Verify the result:

```bash
python3 scripts/pet2dial.py verify
```

For a first successful install where the Dial is already connected, the orchestrator may use:

```bash
python3 scripts/pet2dial.py success-path --upload
```

For service operations:

```bash
python3 scripts/pet2dial.py status
python3 scripts/pet2dial.py logs
python3 scripts/pet2dial.py restart-bridge
python3 scripts/pet2dial.py clear-review-backlog
python3 scripts/pet2dial.py codex-compat
python3 scripts/pet2dial.py uninstall-autostart
```

For T-Encoder Pro operations, use the shared bridge and the T-Encoder firmware target. The minimum open-source flow is:

```bash
python3 scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet init --force
python3 scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet setup-env
python3 scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet setup-board
python3 scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet convert
python3 scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet build
python3 scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet upload
```

## Execution Rules

- Do not copy user-specific pet images, logs, seen-state files, virtual environments, or extracted Codex app bundles into the skill.
- Do not copy the T-Encoder vendor tree into the skill. It is large board-support code and belongs in the target firmware project or an upstream dependency setup step.
- Do not use arbitrary PNGs as the Dial pet source. Use the Codex pet package.
- Do not use LittleFS or runtime asset streaming in the main path.
- Do not include Unit Synth or MIDI cue logic in the main path.
- Keep the firmware resource as one pet by default. Multiple pets consume flash quickly and are outside the success path.
- If the user already has a project directory, preserve user edits unless they approve `--force`.
- After every firmware or bridge edit, run the Python tests and PlatformIO build before upload.
- For T-Encoder Pro firmware edits, also confirm CJK text still uses a UTF-8-capable font, text clipping is pixel-width based, the card remains inside the round safe area, and encoder steps trigger on completed detents to avoid accidental jumps.
- `run-bridge` must self-heal the generated project, venv, and bridge dependencies before starting.
- `run-bridge` should print next actions for ordinary users when it fails, not raw Python tracebacks as the primary output.
- On macOS, prefer the generated `CodexDialBridge.app` wrapper for BLE access because Python without a Bluetooth usage description can be killed by TCC.
- Use `--global-python` only as an advanced escape hatch for users who understand their Python environment.

## Board Targets

`m5dial`:

- Default target and generated project path: `~/CodexDialPet`.
- Firmware template is owned by this skill under `templates/project/firmware`.
- PlatformIO environment: `m5dial`.
- Board: M5Stack Dial / M5StampS3.

`t-encoder-pro`:

- Same bridge and BLE protocol as `m5dial`; do not create a second bridge, state store, BLE name, or skill.
- Recommended generated project path: `~/CodexTEncoderPet`.
- PlatformIO environment: `t_encoder_pro`.
- Board config: `4d_systems_esp32s3_gen4_r8n16`, large 16MB partition, T-Encoder vendor libraries, `ArduinoJson`, and `U8g2`.
- Firmware display: 390x390 CO5300 round display with CST816 touch and physical encoder.
- Proven boot log includes `canvas ready`, `CST816 touch ready`, `pet scale buffer ready`, `Codex T-Encoder Pro firmware ready`, and `BLE client connected`.

## State Model

Pet visual state:

- `idle` maps to atlas row 0 when BLE is connected and no waiting, failed, review, or running state is active.
- `running-right` maps to atlas row 1 as a short Dial-local action while rotating the task selector forward.
- `running-left` maps to atlas row 2 as a short Dial-local action while rotating the task selector backward.
- `waving` maps to atlas row 3 as a short Dial-local action after BLE connect or wake-style local events.
- `jumping` maps to atlas row 4 as a short Dial-local action when the user taps the pet view.
- `failed` maps to atlas row 5 when a recent Codex rollout state is `turn_aborted`, `task_failed`, or `task_cancelled`.
- `waiting` maps to atlas row 6 when BLE is disconnected or the bridge explicitly sends `waiting`.
- `running` maps to atlas row 7 when the bridge sends `mode="running"`.
- `review` maps to atlas row 8 when the bridge sends `mode="review"`.

Task card state:

- Bridge reads local Codex rollout JSONL files.
- `user_message` or active output makes a thread `running`.
- `event_msg.payload.type == "task_complete"` makes a thread `review`.
- Structured waiting events such as `approval_request`, `request_user_input`, `waiting_on_approval`, and `waiting_on_user_input` make a thread `waiting` while recent.
- `turn_aborted`, `task_failed`, and `task_cancelled` make a thread `failed` while recent.
- The pet view shows compact global counts as two rows, `W# F#` above `V# R#`; the pet animation itself carries the highest-priority state.
- Task cards use full labels: `WAITING`, `FAILED`, `REVIEW`, and `RUNNING`.
- Card and pet priority order is `waiting > failed > review > running > idle`.
- `CLICK|thread_id` opens the Codex thread.
- `LEAVE|thread_id` marks the opened review turn as seen using `thread_id + turn_id`.
- Existing historical `task_complete` threads should be baselined as seen so the Dial starts with the current Codex experience, not an old completion backlog.

## Subagents

None. The orchestrator executes this skill sequentially.

## Validation

Run structural validation on the skill:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/skillmaker/scripts/quick_validate.py" <path-to-pet2dial>
```

Run project validation after generating a project:

```bash
python3 -m unittest discover -s tests
python3 scripts/pet2dial.py --project ~/CodexDialPet codex-compat
python3 scripts/pet2dial.py --project ~/CodexDialPet verify
```

Firmware proof is a successful PlatformIO build and upload. Runtime proof is a bridge log showing `Connected. Syncing Codex state.` followed by `Sync pet=<pet-id> mode=<waiting|failed|review|running|idle> bubbles=...`.

Service proof is:

- `python3 scripts/pet2dial.py status` reports the LaunchAgent as loaded.
- `python3 scripts/pet2dial.py logs` shows recent bridge scanning, connection, or sync lines.
