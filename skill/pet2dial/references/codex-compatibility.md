# Codex Compatibility Contract

Pet2Dial is coupled to Codex Desktop in a narrow way. This document records the public, portable contract that the open-source project relies on, plus the local checks to run when Codex changes.

## Baseline

Current support target:

- macOS
- Codex Desktop
- M5Stack Dial / M5StampS3
- T-Encoder Pro as an alternate firmware target sharing the same bridge and BLE contract
- Python 3.10+
- PlatformIO
- Bluetooth Low Energy

Windows and Linux are not supported by the current success path. They may be possible, but they need separate work for Codex home discovery, BLE permissions, background service setup, serial port discovery, and URL opening.

## Portable Paths

Use symbolic paths in docs and code:

```text
<codex-home>
<project>
<pet-id>
```

Default macOS values:

```text
<codex-home> = ~/.codex
<project> = ~/CodexDialPet
Codex app = /Applications/Codex.app
```

Open-source files must not contain user-specific absolute paths such as `/Users/<name>/...`, copied Codex session logs, generated pet frames from a user's private pet, extracted app bundles, or local compatibility snapshots.

## Stable Integration Surfaces

Pet2Dial currently depends on these Codex surfaces:

```text
<codex-home>/config.toml
<codex-home>/pets/<pet-id>/pet.json
<codex-home>/pets/<pet-id>/spritesheet.webp
<codex-home>/sessions/**/rollout-*.jsonl
codex://threads/<thread_id>
```

Selected pet:

```toml
selected-avatar-id = "custom:<pet-id>"
```

The older first-awake UI history in `<codex-home>/.codex-global-state.json` is a fallback only. It is not the primary selected-pet contract.

## Pet Atlas Contract

Pet2Dial expects a Codex-compatible custom pet atlas:

```text
spritesheet.webp
1536x1872 atlas
192x208 source cells
8 columns
9 animation rows
```

Animation rows:

```text
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

Firmware output:

```text
single pet
96x96 frames
8 frames per row
9 rows
RGB565
```

## Task State Contract

The bridge sends one active pet mode plus state counts and task cards:

```json
{
  "v": 1,
  "pet": "<pet-id>",
  "mode": "idle|waiting|failed|review|running",
  "counts": {
    "waiting": 0,
    "failed": 0,
    "review": 0,
    "running": 0
  },
  "bubbles": [
    {
      "thread_id": "<codex-thread-id>",
      "title": "<compact-title>",
      "state": "waiting|failed|review|running",
      "updated_at": 0,
      "cwd": "<session-cwd>",
      "turn_id": "<codex-turn-id>"
    }
  ]
}
```

Priority:

```text
waiting > failed > review > running > idle
```

The pet view displays compact counts in two rows:

```text
W#  F#
V#  R#
```

The pet animation carries the highest-priority active state. The pet view does not show a separate full-text primary label.

## Rollout Fallback

The open-source bridge currently uses local rollout JSONL files as the default state source. It maps observed rollout signals into the official pet vocabulary:

- `task_complete` -> `review`
- active user/assistant output -> `running`
- `approval_request`, `request_user_input`, `waiting_on_approval`, `waiting_on_user_input` -> `waiting`
- `turn_aborted`, `task_failed`, `task_cancelled` -> `failed`

Review cards are governed by Pet2Dial's own seen-state file:

```text
<project>/state/seen_done_threads.json
```

Clicking a review card opens the thread. Leaving the card marks that completed turn as seen.

The same wire schema is used by M5Stack Dial and T-Encoder Pro. Board-specific firmware must adapt display, input, font, and layout without changing bridge state semantics.

## Dial Local Actions

These rows are driven by physical Dial interaction rather than long-lived Codex task state:

- `running-right`: rotate forward through cards
- `running-left`: rotate backward through cards
- `jumping`: tap the pet view
- `waving`: BLE connect or wake-style local action

These actions are short transient overrides. After the action timeout, firmware returns to the long-lived bridge mode.

## Internal Codex Signals

Codex Desktop internal Electron/app-server fields can help explain behavior during audits, but they are not treated as a stable open-source dependency. Previously observed useful signals include:

```text
status.type
activeFlags
waitingOnUserInput
waitingOnApproval
stream-state-changed
thread-read-state-changed
```

Do not hard-code extracted bundle filenames or local asar extraction paths into the project. If a stable Codex external state API appears later, it should feed the same wire schema and priority order.

## Compatibility Check

Run this after Codex upgrades or when pet/task state behavior looks wrong:

```bash
python3 skill/pet2dial/scripts/pet2dial.py codex-compat
```

The command writes a local snapshot:

```text
<project>/state/codex_compat_snapshot.json
```

The snapshot may include local paths, selected pet id, Codex app version, `app.asar` hash, pet atlas geometry, and detected rollout event types. It is local diagnostic state and should not be committed.

Useful drift signals:

- Codex app version or `app.asar` hash changed
- selected pet id changed unexpectedly
- pet atlas geometry changed from 8x9 / 1536x1872
- rollout event names no longer include expected running/review/waiting/failed sources
- `codex://threads/<thread_id>` no longer opens the expected conversation

When drift is detected, update this compatibility document first, then update code and tests.
