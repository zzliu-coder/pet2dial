# M5Stack Global Innovation Contest 2026 Form Draft

Use these answers after the Hackster project is published.

## Project Title

Pet2Dial: A Physical Codex Pet on M5Stack Dial

## Project URL

To be filled after Hackster publishing.

## GitHub Repository

To be filled after GitHub publishing.

## Short Description

Pet2Dial moves the Codex desktop pet onto an M5Stack Dial. It converts the selected Codex custom pet into Dial firmware, then uses BLE to sync live running and review tasks from Codex Desktop. The Dial becomes a tactile AI workspace companion with rotary task browsing and tap-to-open conversation navigation.

## Hardware Used

- M5Stack Dial with M5StampS3 controller
- Mac running Codex Desktop
- USB-C cable for firmware flashing
- Bluetooth Low Energy for sync

## Software Used

- Codex Desktop
- Python
- PlatformIO
- Arduino framework for ESP32-S3
- M5Dial library
- M5GFX
- ArduinoJson
- bleak
- Pillow

## Category

AI-powered tool / productivity device / creative hardware interface

## What Makes It Special

Pet2Dial is a physical extension of an AI coding workspace. It does not simply show notifications; it mirrors the user's actual Codex pet and task state. The Dial's round display, touch input, and rotary encoder turn agent status into a small tangible interface that stays visible without occupying the Mac screen.

## How M5Stack Is Used

The M5Stack Dial is the main controller and user interface. Its ESP32-S3 runs the firmware, renders the animated pet and task card UI, handles touch and rotary encoder input, and exposes a BLE peripheral named `CodexDial`. The Mac bridge connects to that BLE peripheral and streams Codex state to the device.

## Build Instructions Summary

1. Install the skill/repository.
2. Run `python3 skill/pet2dial/scripts/pet2dial.py doctor`.
3. Run `python3 skill/pet2dial/scripts/pet2dial.py success-path --upload` with the Dial connected by USB.
4. Run `python3 skill/pet2dial/scripts/pet2dial.py run-bridge`.
5. The Dial displays the selected Codex pet and live running/review task cards over BLE.

## 中文摘要

Pet2Dial 是一个把 Codex 桌面宠物搬到 M5Stack Dial 上的硬件项目。它读取 Codex 当前选择的 custom pet，转换成 Dial 固件资源，并用蓝牙同步 Codex 的运行中任务和待 review 任务。用户可以旋转 Dial 浏览任务卡片，点击卡片打开对应的 Codex 会话。
