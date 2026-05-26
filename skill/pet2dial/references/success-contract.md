# Pet2Dial Success Contract

## Use Cases

Use Case: First install on a Mac with a connected M5Stack Dial
Trigger: "Put my Codex pet on this Dial."
Steps: Run doctor, initialize project, install dependencies, convert selected Codex pet, build, upload, run bridge.
Result: Dial shows the selected Codex pet and receives running/review task cards over BLE.

Use Case: Refresh after the user changes Codex pet
Trigger: "I changed my Codex pet; refresh the Dial."
Steps: Run doctor, convert the newly selected Codex pet, build, upload, run bridge.
Result: Dial displays the newly selected pet.

Use Case: Reconnect after reboot
Trigger: "My Dial restarted; sync it again."
Steps: Run bridge. If firmware is already flashed, no USB upload is required.
Result: Dial reconnects over BLE and shows current Codex state.

## Fixed Success Path

The visual source is the Codex custom pet package:

```text
~/.codex/pets/<pet-id>/pet.json
~/.codex/pets/<pet-id>/spritesheet.webp
```

The atlas is treated as official Codex pet geometry:

```text
atlas: 1536x1872
cell: 192x208
columns: 8
rows: 9
states:
  0 idle
  1 running-right
  2 running-left
  3 waving
  4 jumping
  5 failed
  6 waiting
  7 running
  8 review
```

The firmware resource is:

```text
one pet
96x96 frame
8 frames per row
9 rows
RGB565
transparent pixels precomposited against the Dial background color
```

This is the path that produced stable color, stable animation, and acceptable flash use. Treat it as the default, not as an option among many.

## Device Contract

Firmware:

- Board: M5Stack Dial / M5StampS3
- Display: 240x240 circular TFT
- BLE peripheral name: `CodexDial`
- State write protocol: chunked `CD1|seq|idx|total|json-part`
- Event notify protocol: `CLICK|thread_id` and `LEAVE|thread_id`

Bridge:

- macOS process acts as BLE central.
- Bridge reads Codex local files from `~/.codex`.
- Bridge writes only its own generated project state under `<project>/state`.
- Bridge opens Codex conversations with `codex://threads/<thread_id>`.

## Task State Contract

Dial cards include only:

- `running`
- `review`, derived from rollout `task_complete`

Dial cards exclude:

- `turn_aborted`
- review threads already marked seen by this bridge

Review visibility rule:

- Clicking a review card opens the Codex conversation.
- The card remains in the current list while the user keeps viewing it.
- The card is marked seen only after the Dial sends `LEAVE`.
- `LEAVE` is sent when the user rotates away from that card or leaves card view.

## Environment Contract

The successful Mac environment has:

- macOS
- Python 3.10+
- `venv`
- PlatformIO in the generated project venv
- Python packages from `requirements.txt`: `bleak`, `Pillow`
- a visible Dial serial device during upload, usually `/dev/cu.usbmodem*`
- Bluetooth permission for the process running the bridge

The skill should install project-local Python dependencies and PlatformIO into the generated project venv. It should not require global Python package installation.

## Open Source Boundary

The skill package must not include:

- a user's `spritesheet.webp`
- generated `pet_frames.h`
- `.venv`
- `.pio`
- `logs`
- `state/seen_done_threads.json`
- extracted Codex app bundles
- private rollout files

The skill may include:

- source templates
- bridge source
- firmware source
- deterministic conversion scripts
- environment and verification scripts
