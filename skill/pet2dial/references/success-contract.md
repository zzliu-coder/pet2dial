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

Use Case: Daily background sync
Trigger: "Keep my Dial synced after I log in."
Steps: Install the LaunchAgent. The agent launches the macOS bridge app, which starts the project venv bridge and writes logs.
Result: The user does not need a terminal window; `status`, `restart-bridge`, and `logs` expose health.

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
- Daily bridge mode uses an isolated project venv, a generated `CodexDialBridge.app` with Bluetooth usage description, and an optional user LaunchAgent.
- Advanced users may run with global Python, but the open-source success path should prefer the isolated venv.

## Task State Contract

Dial cards include only:

- `running`
- `review`, derived from rollout `task_complete`

Dial cards exclude:

- `turn_aborted`
- review threads already marked seen by this bridge

`turn_aborted` can still drive the visual pet mode `failed` for a short recent failure window. It does not become a Dial task card.

Review visibility rule:

- Clicking a review card opens the Codex conversation.
- The card remains in the current list while the user keeps viewing it.
- The card is marked seen only after the Dial sends `LEAVE`.
- `LEAVE` is sent when the user rotates away from that card or leaves card view.

## Codex Data Contract

Pet source:

- `~/.codex/pets/<pet-id>/pet.json`
- `~/.codex/pets/<pet-id>/spritesheet.webp`
- selected custom pet id from `~/.codex/config.toml` `selected-avatar-id = "custom:<pet-id>"` when present
- older UI first-awake custom pet history from `~/.codex/.codex-global-state.json` only as fallback

Pet atlas rows mirror the Codex pet package shape:

- `idle`
- `running-right`
- `running-left`
- `waving`
- `jumping`
- `failed`
- `waiting`
- `running`
- `review`

Task source:

- local Codex rollout JSONL files under `~/.codex/sessions`
- `session_meta.payload.cwd`
- `response_item.payload` user messages
- `event_msg.payload.type`
- `event_msg.payload.message`
- `event_msg.payload.turn_id`

State source:

- Pet2Dial's open-source default is rollout fallback mode.
- Rollout fallback emits only official Codex pet state names.
- Rollout fallback approximates `review` from new `task_complete` turns after baseline.
- Rollout fallback approximates `waiting` from structured waiting event types such as `approval_request`, `request_user_input`, `waiting_on_approval`, and `waiting_on_user_input`.
- If a future stable Codex app-server state API is available, it should feed the same official state names and priority order without changing the Dial wire contract.

Bridge wire schema:

```json
{
  "v": 1,
  "pet": "<pet-id>",
  "mode": "idle|waiting|failed|running|review",
  "now": 0,
  "bubbles": [
    {
      "thread_id": "<codex-thread-id>",
      "title": "<compact-user-visible-title>",
      "state": "running|review",
      "updated_at": 0,
      "cwd": "<session-cwd>",
      "turn_id": "<codex-turn-id>"
    }
  ]
}
```

Allowed local bridge state:

- `<project>/state/seen_done_threads.json`, schema v2, which stores review turn ids already seen through this bridge and a fallback baseline timestamp.

Keep this contract narrow. Do not add independent pet catalogs, fake default pet ids, multi-pet firmware bundles, or task states that the bridge does not actually send.

## Pet Animation State Contract

The source atlas contains all Codex pet rows. Pet2Dial uses every row, with long-lived modes coming from Codex state and short actions coming from real Dial interaction:

```text
0 idle           connected, no running/review/recent failed mode
1 running-right  transient while rotating forward through task cards
2 running-left   transient while rotating backward through task cards
3 waving         transient after BLE connect or tap-to-open
4 jumping        transient when a new running/review card appears
5 failed         recent Codex `turn_aborted`, with no running/review card taking priority
6 waiting        BLE disconnected or explicit bridge waiting mode
7 running        bridge mode from active Codex rollout activity
8 review         bridge mode from unseen Codex `task_complete`
```

Priority order in firmware:

```text
BLE disconnected -> waiting
active transient action -> running-right/running-left/waving/jumping
bridge mode failed -> failed
bridge mode running -> running
bridge mode review -> review
bridge mode waiting -> waiting
default -> idle
```

Bridge mode priority:

```text
waiting > failed > running > review > idle
```

## Environment Contract

The successful Mac environment has:

- macOS
- Python 3.10+
- `venv`
- PlatformIO in the generated project venv
- Python packages from `requirements.txt`: `bleak`, `Pillow`
- a visible Dial serial device during upload, usually `/dev/cu.usbmodem*`
- Bluetooth permission for the process running the bridge
- a generated app wrapper for macOS BLE permission prompts
- optional LaunchAgent at `~/Library/LaunchAgents/local.codex.dial.bridge.plist`

The skill should install project-local Python dependencies and PlatformIO into the generated project venv. It should not require global Python package installation.

## Service Health Contract

`run-bridge` is a user command, not a developer-only command. It should:

- initialize the generated project if it is missing
- create the project venv if it is missing
- install missing bridge dependencies into that venv
- create the macOS bridge app wrapper
- start the bridge
- explain the next action when it fails

The service commands are:

```text
install-autostart
uninstall-autostart
status
restart-bridge
logs
```

`doctor` should report:

- Codex home and session availability
- selected or newest local custom pet
- pet package presence
- Dial USB serial visibility
- generated project and venv state
- bridge dependency state
- PlatformIO availability
- bridge app presence
- LaunchAgent installation and loaded status
- recent bridge connection and sync evidence when logs exist

If the bridge cannot find `CodexDial`, prefer a concrete diagnosis:

- Dial firmware may still be in download mode
- Dial may need a physical reset
- BLE permission may be missing
- firmware may not be advertising the expected service/name

Review backlog behavior:

- `review` is derived from `event_msg.payload.type == "task_complete"`.
- The bridge does not use an independent `done` state in its public wire schema.
- On first bridge state initialization or v1 state upgrade, existing historical `task_complete` turns are marked seen so the Dial does not show old Codex completions as current review cards.
- Seen state is keyed by `thread_id + turn_id`, so a later completion in the same conversation can become a fresh review card.
- `clear-review-backlog` marks all currently completed rollout turns as seen and refreshes the fallback baseline without modifying Codex session files.

macOS bridge wrapper behavior:

- The generated bridge app must include `NSBluetoothAlwaysUsageDescription` so CoreBluetooth access is authorized through macOS privacy controls.
- The generated bridge app must include `LSUIElement = true` because it is a background device service.
- Thread-opening must log the attempted `codex://threads/<thread_id>` URL result so click failures can be traced to Dial events, BLE delivery, or macOS URL handling.

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
- user-specific generated LaunchAgent plists
- user-specific bridge app bundles

The skill may include:

- source templates
- bridge source
- firmware source
- deterministic conversion scripts
- environment and verification scripts
