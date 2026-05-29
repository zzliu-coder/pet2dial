# T-Encoder Pro Target

## Position

T-Encoder Pro belongs inside `pet2dial` as a hardware target. It solves the same product problem as M5Stack Dial: mirror the selected Codex pet and Codex task state onto a small round BLE display.

Keep these surfaces shared with the default Dial path:

- Codex pet package source under `~/.codex/pets/<pet-id>`
- 96x96 RGB565 pet frame resource generated from the official 8x9 Codex atlas
- BLE name `CodexDial`
- BLE service and characteristic UUIDs
- chunked `CD1|seq|idx|total|json-part` state writes
- `CLICK|thread_id` and `LEAVE|thread_id` events
- `waiting > failed > review > running > idle` priority
- review seen-state rule: click opens the Codex thread; leave marks the review turn seen
- bridge project, LaunchAgent, and state files from the normal pet2dial path

## Local Project From Migration Run

Recommended generated project path:

```bash
~/CodexTEncoderPet
```

The firmware lives under:

```bash
~/CodexTEncoderPet/firmware
```

The bridge package and state model are generated into the same project. It still advertises and scans for the shared BLE name `CodexDial`.

## Firmware Contract

PlatformIO environment:

```text
[env:t_encoder_pro]
platform = espressif32
board = 4d_systems_esp32s3_gen4_r8n16
framework = arduino
upload_speed = 921600
board_build.partitions = large_spiffs_16MB.csv
lib_extra_dirs = ../vendor/T-Encoder-Pro/libraries
lib_deps = bblanchon/ArduinoJson@^7.2.0, olikraus/U8g2
```

Hardware-specific responsibilities:

- CO5300 390x390 round display through Arduino GFX
- CST816 touch initialization and tap handling
- physical encoder and button handling
- round-display safe-area layout
- CJK-capable UTF-8 text rendering with U8g2
- pixel-width based title and cwd clipping
- card, counts, focus animation, and pet animation matching the pet2dial semantics
- detent-complete encoder stepping to reduce accidental jumps and flicker

Keep the boot log useful. A healthy upload/run should show lines like:

```text
canvas ready
CST816 touch ready
pet scale buffer ready
Codex T-Encoder Pro firmware ready
BLE client connected
```

## Proven Commands

Initialize:

```bash
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet init --force
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet setup-env
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet setup-board
```

Convert the selected Codex pet, build, and upload:

```bash
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet convert
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet build
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet upload
```

For a first install with the device already connected over USB:

```bash
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet success-path --upload
```

Verify the shared bridge:

```bash
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet status
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet logs
```

Clear historical review backlog when the user explicitly wants the display to start from current Codex state:

```bash
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet clear-review-backlog
```

## Evidence From The Migration

The migration implementation added or preserved:

- U8g2 CJK font support for Chinese title and cwd text
- pixel-width clipping instead of character-count clipping
- round-safe card layout and removal of temporary outer-ring visuals
- focus animation for selected task cards
- CLICK/LEAVE behavior aligned with pet2dial review semantics
- encoder stepping based on completed detents
- successful PlatformIO build
- successful USB upload on a detected `/dev/cu.usbmodem*` serial port
- upload hash verification
- bridge reconnection with the selected Codex custom pet

Do not treat a local pet id or upload port as a default.
