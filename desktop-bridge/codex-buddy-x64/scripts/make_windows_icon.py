#!/usr/bin/env python3
"""Create the Windows .ico app icon from the PixelMug Codex PNG."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


ICO_SIZES = ((16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256))


def make_base_icon(source: Path) -> Image.Image:
    icon = Image.open(source).convert("RGBA")
    if icon.size == (1024, 1024):
        return icon

    icon.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (1024, 1024), (255, 255, 255, 255))
    x = (canvas.width - icon.width) // 2
    y = (canvas.height - icon.height) // 2
    canvas.paste(icon, (x, y), icon)
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description="Build PixelMug Codex Windows .ico")
    parser.add_argument("--source", type=Path, default=Path("assets/1024.png"))
    parser.add_argument("--out", type=Path, default=Path("assets/pixelmug-codex.ico"))
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    make_base_icon(args.source).save(args.out, sizes=ICO_SIZES)
    print(f"Created {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
