#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


CELL_W = 192
CELL_H = 208
COLS = 8
ROWS = 9


DISPLAY_BG = (17, 23, 28)
DEFAULT_ROWS = tuple(range(ROWS))
ROW_NAMES = {
    0: "IDLE",
    1: "RUNNING_RIGHT",
    2: "RUNNING_LEFT",
    3: "WAVING",
    4: "JUMPING",
    5: "FAILED",
    6: "WAITING",
    7: "RUNNING",
    8: "REVIEW",
}


def rgb565_from_rgb(r: int, g: int, b: int) -> int:
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def rgb565(pixel: tuple[int, int, int, int]) -> int:
    r, g, b, a = pixel
    alpha = a / 255.0
    bg_r, bg_g, bg_b = DISPLAY_BG
    out_r = round((r * alpha) + (bg_r * (1.0 - alpha)))
    out_g = round((g * alpha) + (bg_g * (1.0 - alpha)))
    out_b = round((b * alpha) + (bg_b * (1.0 - alpha)))
    return rgb565_from_rgb(out_r, out_g, out_b)


def parse_rows(value: str) -> tuple[int, ...]:
    rows = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not rows:
        raise SystemExit("At least one row is required")
    for row in rows:
        if row < 0 or row >= ROWS:
            raise SystemExit(f"Invalid row {row}; expected 0..{ROWS - 1}")
    return rows


def nonempty_columns(image: Image.Image, row: int, frames: int) -> list[int]:
    valid: list[int] = []
    for col in range(min(frames, COLS)):
        cell = image.crop((col * CELL_W, row * CELL_H, (col + 1) * CELL_W, (row + 1) * CELL_H))
        if cell.getchannel("A").getbbox() is not None:
            valid.append(col)
    return valid


def frame_sequence(valid_cols: list[int], target_frames: int) -> list[int]:
    if not valid_cols:
        return [0] * target_frames
    if len(valid_cols) == 1:
        return [valid_cols[0]] * target_frames

    cycle = valid_cols + valid_cols[-2:0:-1]
    return [cycle[idx % len(cycle)] for idx in range(target_frames)]


def load_pet_frames(pet_name: str, size: int, frames: int, rows: tuple[int, ...], codex_home: Path) -> list[list[int]]:
    pet_dir = codex_home / "pets" / pet_name
    manifest = pet_dir / "pet.json"
    if not manifest.exists():
        raise SystemExit(f"Missing pet manifest: {manifest}")

    spritesheet = pet_dir / "spritesheet.webp"
    if not spritesheet.exists():
        raise SystemExit(f"Missing spritesheet: {spritesheet}")

    image = Image.open(spritesheet).convert("RGBA")
    expected = (CELL_W * COLS, CELL_H * ROWS)
    if image.size != expected:
        raise SystemExit(f"Unexpected spritesheet size {image.size}; expected {expected}")

    selected: list[list[int]] = []
    for row in rows:
        for col in frame_sequence(nonempty_columns(image, row, frames), min(frames, COLS)):
            cell = image.crop((col * CELL_W, row * CELL_H, (col + 1) * CELL_W, (row + 1) * CELL_H))
            cell.thumbnail((size, size), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            canvas.alpha_composite(cell, ((size - cell.width) // 2, (size - cell.height) // 2))
            pixel_source = canvas.get_flattened_data() if hasattr(canvas, "get_flattened_data") else canvas.getdata()
            selected.append([rgb565(pixel) for pixel in pixel_source])
    return selected


def discover_pets(codex_home: Path) -> list[str]:
    pets_dir = codex_home / "pets"
    if not pets_dir.exists():
        return []
    return sorted(folder.name for folder in pets_dir.iterdir() if (folder / "pet.json").exists() and (folder / "spritesheet.webp").exists())


def row_slot(rows: tuple[int, ...], source_row: int) -> int:
    try:
        return rows.index(source_row)
    except ValueError:
        return 0


def convert(pet_name: str, out: Path, size: int, frames: int, rows: tuple[int, ...], codex_home: Path) -> None:
    pet_names = discover_pets(codex_home) if pet_name == "all" else [pet_name]
    if not pet_names:
        raise SystemExit(f"No pets found under {codex_home / 'pets'}")
    loaded = [(name, load_pet_frames(name, size, frames, rows, codex_home)) for name in pet_names]

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        handle.write("#pragma once\n")
        handle.write("#include <Arduino.h>\n\n")
        handle.write(f"static constexpr uint16_t PET_FRAME_SIZE = {size};\n")
        handle.write(f"static constexpr uint16_t PET_FRAME_COUNT = {min(frames, COLS)};\n")
        handle.write(f"static constexpr uint16_t PET_STATE_COUNT = {len(rows)};\n")
        for source_row, name in ROW_NAMES.items():
            handle.write(f"static constexpr int PET_ROW_{name} = {row_slot(rows, source_row)};\n")
        handle.write(f"static constexpr uint16_t PET_BACKGROUND_COLOR = 0x{rgb565_from_rgb(*DISPLAY_BG):04x};\n")
        handle.write("struct PetFrameSet { const char* id; const uint16_t* frames; };\n\n")
        for name, pet_frames in loaded:
            symbol = "PET_FRAMES_" + "".join(ch.upper() if ch.isalnum() else "_" for ch in name)
            handle.write(f"static const uint16_t {symbol}[] PROGMEM = {{\n")
            for pixels in pet_frames:
                if len(pixels) != size * size:
                    raise SystemExit(f"Internal frame size mismatch for {name}")
                for idx in range(0, len(pixels), 12):
                    row = ", ".join(f"0x{value:04x}" for value in pixels[idx : idx + 12])
                    handle.write(f"  {row},\n")
            handle.write("};\n\n")

        handle.write("static const PetFrameSet PET_SETS[] = {\n")
        for name, _pet_frames in loaded:
            symbol = "PET_FRAMES_" + "".join(ch.upper() if ch.isalnum() else "_" for ch in name)
            handle.write(f'  {{"{name}", {symbol}}},\n')
        handle.write("};\n")
        handle.write(f"static constexpr uint16_t PET_SET_COUNT = {len(loaded)};\n")
    print(
        f"Wrote {out} ({len(loaded)} pets, {len(rows)} rows, {min(frames, COLS)} frames each, {size}x{size})"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a Codex pet spritesheet into a firmware RGB565 header.")
    parser.add_argument("pet_name", help="Pet id, or 'all' to include every installed Codex pet.")
    parser.add_argument("--out", type=Path, default=Path("firmware/include/pet_frames.h"))
    parser.add_argument("--size", type=int, default=96)
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--rows", default=",".join(str(row) for row in DEFAULT_ROWS))
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    args = parser.parse_args()
    convert(args.pet_name, args.out, args.size, args.frames, parse_rows(args.rows), args.codex_home)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
