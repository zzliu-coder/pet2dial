---
name: pet2dial
description: Mirror the currently selected Codex custom pet and Codex running/review task state onto an M5Stack Dial. Use when the user wants to prepare a Mac, convert the Codex pet atlas, flash Dial firmware, run the BLE bridge, and verify the Codex pet appears on the external Dial display.
---

# Pet2Dial

## Purpose

Put the Codex desktop pet onto an M5Stack Dial using the proven path from this run: one selected Codex custom pet, converted from the official Codex pet atlas into a 96x96 RGB565 firmware resource, flashed into M5Stack Dial firmware, then synchronized from macOS to Dial over BLE.

This skill is a success-path workflow. Keep the main path direct: check environment, create the project, convert the pet, build, upload, run bridge, verify.

## Success Contract

The successful result is:

- Dial firmware is flashed and advertises `CodexDial`.
- The Dial displays the user's selected Codex custom pet with stable color and animation.
- The pet uses official Codex atlas rows: `idle`, `running`, `review`, and `waiting` are mapped to the corresponding Dial states.
- The bridge syncs only active `running` tasks and `task_complete` tasks exposed as `review`.
- Clicking a Dial card opens `codex://threads/<thread_id>`.
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
- BLE name: `CodexDial`

## Required User Conditions

Proceed when:

- The user is on macOS.
- Codex Desktop has at least one custom pet under `~/.codex/pets`.
- The M5Stack Dial is available for USB flashing.
- The user accepts that BLE is used for daily sync after flashing; USB is only needed for firmware upload.

Stop and ask for the smallest missing fact when:

- No Codex custom pet exists.
- Multiple likely USB serial devices exist and the script cannot identify the Dial.
- The user wants to support a different board, a different OS, multiple pets, or runtime pet streaming.

## Workflow

1. Read this skill's `references/success-contract.md`.
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

9. Verify the result:

```bash
python3 scripts/pet2dial.py verify
```

For a first successful install where the Dial is already connected, the orchestrator may use:

```bash
python3 scripts/pet2dial.py success-path --upload
```

## Execution Rules

- Do not copy user-specific pet images, logs, seen-state files, virtual environments, or extracted Codex app bundles into the skill.
- Do not use arbitrary PNGs as the Dial pet source. Use the Codex pet package.
- Do not use LittleFS or runtime asset streaming in the main path.
- Do not include Unit Synth or MIDI cue logic in the main path.
- Keep the firmware resource as one pet by default. Multiple pets consume flash quickly and are outside the success path.
- If the user already has a project directory, preserve user edits unless they approve `--force`.
- After every firmware or bridge edit, run the Python tests and PlatformIO build before upload.

## State Model

Pet visual state:

- `running` maps to the Codex `running` row.
- `review` and `task_complete` map to the Codex `review` row.
- disconnected or waiting maps to the Codex `waiting` row.
- idle maps to the Codex `idle` row.

Task card state:

- Bridge reads local Codex rollout JSONL files.
- `user_message` or active output makes a thread `running`.
- `task_complete` makes a thread `review`.
- `turn_aborted` is filtered out of Dial task cards.
- `CLICK|thread_id` opens the Codex thread.
- `LEAVE|thread_id` marks an opened review card as seen.

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
python3 scripts/pet2dial.py --project ~/CodexDialPet verify
```

Firmware proof is a successful PlatformIO build and upload. Runtime proof is a bridge log showing `Connected. Syncing Codex state.` followed by `Sync pet=<pet-id> mode=<running|review|idle> bubbles=...`.
