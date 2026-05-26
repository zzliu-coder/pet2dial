# Pet2Dial: A Physical Codex Pet on M5Stack Dial

## Elevator Pitch

Pet2Dial recreates the Codex desktop pet on an M5Stack Dial, then turns the Dial into a rotary remote for Codex tasks: rotate to browse, tap to open the matching conversation.

## Story

Modern AI coding tools are powerful, but they also create a new kind of attention problem. When several agents are running, finished, or waiting for review, the user has to keep checking the desktop UI. Pet2Dial moves that status surface onto a tiny piece of hardware and makes it feel like part of the desk.

The idea started from a simple feeling: the Codex pet already makes long-running work feel more alive. I wanted that pet to leave the Mac screen and become a real desk object. The M5Stack Dial is a good fit because it has a circular screen, touch input, a rotary encoder, BLE, and an ESP32-S3 controller in a compact form.

Pet2Dial keeps Codex as the source of truth. The Mac bridge reads the local Codex pet package and task state. The firmware renders a close hardware version of the official pet experience plus a small task UI. Rotating the Dial opens task cards; tapping a card opens the corresponding Codex conversation on the Mac. In daily use it behaves like a small physical pet and a handheld-style remote for the AI workspace.

## What Makes It Special

- It is a physical extension of Codex, with the selected Codex pet moved from the Mac screen onto the desk.
- It works like a rotary task remote: turn the knob to browse running/review tasks and tap to jump back to the exact Codex conversation.
- It uses the official Codex custom pet atlas format instead of arbitrary static images.
- It turns the Dial's rotary encoder into a natural task selector.
- It keeps USB free after flashing by using Bluetooth Low Energy for daily sync.
- It bridges software-agent state into a physical object, making AI work visible without another desktop window.

## Hardware

- M5Stack Dial, powered by M5StampS3
- Mac running Codex Desktop
- USB-C cable for firmware upload
- Bluetooth Low Energy for live sync

Optional:

- A stand, case, or desk mount for better daily use

## Software

- Python 3.10+
- PlatformIO
- Arduino framework for ESP32-S3
- M5Dial library
- M5GFX
- ArduinoJson
- Python `bleak`
- Python `Pillow`

## How It Works

Pet2Dial has three parts.

### 1. Pet Conversion

Codex custom pets are stored locally as:

```text
~/.codex/pets/<pet-id>/pet.json
~/.codex/pets/<pet-id>/spritesheet.webp
```

The converter reads the official 8x9 Codex pet atlas and generates a compact M5Stack Dial firmware header:

```text
96x96 frames
8 frames per animation row
9 animation rows
RGB565 color
single selected pet
```

Keeping one pet in firmware is a deliberate design choice. It keeps flash usage predictable and makes the first install reliable.

### 2. Dial Firmware

The firmware runs on the M5Stack Dial. It:

- renders the selected pet
- animates `idle`, `running`, `review`, and `waiting` states
- shows running and review counters
- opens a task card UI when the rotary encoder is turned
- sends tap and leave events back to the Mac over BLE

The firmware advertises as:

```text
CodexDial
```

### 3. Mac Bridge

The Mac bridge reads Codex local state and writes compact JSON frames to the Dial over BLE.

It syncs:

- currently selected pet id
- current mode: idle, running, review, waiting
- running task cards
- completed tasks waiting for review

The event protocol is intentionally small:

```text
CLICK|<thread_id>  open the matching Codex thread
LEAVE|<thread_id>  mark a reviewed card as seen
```

This lets a review card remain visible while the user is still looking at it. The card disappears only after the user rotates away or returns to the pet view.

## Build Steps

Clone the repository:

```bash
git clone https://github.com/codingbull87/pet2dial.git
cd pet2dial
```

Run the environment check:

```bash
python3 skill/pet2dial/scripts/pet2dial.py doctor
```

Create the generated working project:

```bash
python3 skill/pet2dial/scripts/pet2dial.py init --force
```

Install local dependencies:

```bash
python3 skill/pet2dial/scripts/pet2dial.py setup-env
```

Convert the currently selected Codex pet:

```bash
python3 skill/pet2dial/scripts/pet2dial.py convert
```

Build the firmware:

```bash
python3 skill/pet2dial/scripts/pet2dial.py build
```

Connect the M5Stack Dial over USB and upload:

```bash
python3 skill/pet2dial/scripts/pet2dial.py upload
```

Run the BLE bridge:

```bash
python3 skill/pet2dial/scripts/pet2dial.py run-bridge
```

## Validation

The project validates the successful path before flashing:

- checks macOS, Python, Codex home, Codex pet files, and Dial USB serial device
- creates an isolated Python virtual environment
- installs PlatformIO locally
- converts the selected Codex pet atlas
- builds the firmware
- verifies that the bridge can produce a live Codex snapshot

Observed firmware usage from the working prototype:

```text
RAM:   15.4%
Flash: 78.9%
```

## Demo Script

1. Show Codex Desktop with a custom pet selected.
2. Show the M5Stack Dial displaying the same pet.
3. Start or finish a Codex task.
4. Show the Dial counter changing from `V0` to `V1`.
5. Rotate the Dial to open the task card.
6. Tap the card and show Codex opening the matching conversation.
7. Rotate away and show the review card leaving the queue.

## Why M5Stack Dial

The Dial is the right form factor for this idea:

- the round display makes the pet feel like a small physical presence
- the rotary encoder is ideal for browsing multiple agent tasks
- touch input gives direct open/confirm behavior
- BLE keeps the Mac port free after flashing
- the ESP32-S3 is powerful enough for a smooth animated UI

## What I Learned

The biggest challenge was visual fidelity. A direct image-to-screen attempt looked washed out and flickery. The stable path was to respect the Codex pet atlas, preconvert the frames, use one selected pet, and keep the firmware rendering simple.

The second challenge was review semantics. A finished task should not disappear the moment it is tapped. Pet2Dial uses a `CLICK` plus `LEAVE` event model so the user controls when a reviewed item leaves the visible queue.

## Future Work

- Package the bridge as a native macOS menu bar app.
- Add a small generated demo video flow.
- Support resource storage outside firmware after the first success path is stable.
- Add more Dial UI themes while keeping the pet readable.

## GitHub

Repository:

```text
https://github.com/codingbull87/pet2dial
```

## 中文摘要

Pet2Dial 把 Codex 桌面里的宠物搬到 M5Stack Dial 上。它读取 Codex 当前选中的 custom pet，把官方宠物 atlas 转成 Dial 固件资源，刷入 M5Stack Dial，然后通过蓝牙同步 Codex 的运行中任务和待 review 任务。旋转 Dial 可以切换任务卡片，点击卡片会打开对应的 Codex 会话。

这个项目的重点是把 AI 工作流从电脑屏幕里拿出来，变成桌面上的一个可触摸、可旋转、可一眼看到状态的硬件伴侣。
