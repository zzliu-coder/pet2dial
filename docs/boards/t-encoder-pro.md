# LilyGO T-Encoder Pro

Pet2Dial supports LilyGO T-Encoder Pro as a second hardware target using the same Codex pet source, BLE bridge, task cards, and `CLICK` / `LEAVE` semantics as the M5Stack Dial target.

## Hardware

- Board: LilyGO T-Encoder Pro
- Display: 390x390 CO5300 circular display
- Input: CST816 touch plus physical encoder and button
- BLE name: `CodexDial`
- PlatformIO environment: `t_encoder_pro`

## Dependency Model

The T-Encoder Pro board support package is large, so it is downloaded into the generated project and ignored by git.

Pet2Dial pins the vendor checkout to:

```text
https://github.com/Xinyuan-LilyGO/T-Encoder-Pro.git
5f5c3bf6a714991001d385ca8c13ca75a41c5a98
```

The vendor checkout is created by:

```bash
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet setup-board
```

## First Install

```bash
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet init --force
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet setup-env
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet setup-board
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet convert
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet build
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet upload
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet install-autostart
```

With the device already connected over USB:

```bash
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet success-path --upload
```

## Public Repo Boundary

Commit the T-Encoder Pro firmware template and docs. Do not commit:

```text
~/CodexTEncoderPet/vendor/
~/CodexTEncoderPet/firmware/.pio/
~/CodexTEncoderPet/firmware/include/pet_frames.h
~/CodexTEncoderPet/logs/
~/CodexTEncoderPet/state/
```

The generated `pet_frames.h` contains the user's local Codex pet. The repository keeps only the placeholder file that tells users to run `convert`.
