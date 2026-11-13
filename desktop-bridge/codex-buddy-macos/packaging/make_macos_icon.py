#!/usr/bin/env python3
"""Create the macOS .icns app icon from the PixelMug PNG logo."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image


ICON_SIZES = (16, 32, 128, 256, 512)


def _hex_color(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise argparse.ArgumentTypeError("background must be a 6-digit hex color")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _corner_background(image: Image.Image, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    width, height = image.size
    corners = (
        image.getpixel((0, 0)),
        image.getpixel((width - 1, 0)),
        image.getpixel((0, height - 1)),
        image.getpixel((width - 1, height - 1)),
    )
    opaque = [pixel[:3] for pixel in corners if len(pixel) < 4 or pixel[3] > 0]
    if not opaque:
        return fallback
    return tuple(round(sum(pixel[i] for pixel in opaque) / len(opaque)) for i in range(3))


def make_base_icon(source: Path, background: tuple[int, int, int]) -> Image.Image:
    icon = Image.open(source).convert("RGBA")
    if icon.size != (1024, 1024):
        icon.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (1024, 1024), (*_corner_background(icon, background), 255))
        x = (canvas.width - icon.width) // 2
        y = (canvas.height - icon.height) // 2
        canvas.paste(icon, (x, y), icon)
        icon = canvas

    alpha = icon.getchannel("A")
    if alpha.getextrema() != (255, 255):
        bg = _corner_background(icon, background)
        canvas = Image.new("RGBA", icon.size, (*bg, 255))
        canvas.paste(icon, (0, 0), icon)
        icon = canvas

    return icon


def save_iconset(base: Image.Image, iconset: Path) -> None:
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True)

    for size in ICON_SIZES:
        one_x = base.resize((size, size), Image.Resampling.LANCZOS)
        two_x = base.resize((size * 2, size * 2), Image.Resampling.LANCZOS)
        one_x.save(iconset / f"icon_{size}x{size}.png")
        two_x.save(iconset / f"icon_{size}x{size}@2x.png")


def save_icns(base: Image.Image, iconset: Path, out: Path) -> None:
    try:
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)
        return
    except subprocess.CalledProcessError:
        pass

    with tempfile.TemporaryDirectory(prefix="pixelmug-icon-") as tmp:
        source_png = Path(tmp) / "icon.png"
        source_tiff = Path(tmp) / "icon.tiff"
        base.save(source_png)
        subprocess.run(["sips", "-s", "format", "tiff", str(source_png), "--out", str(source_tiff)], check=True)
        subprocess.run(["tiff2icns", str(source_tiff), str(out)], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build PixelMug Codex .icns")
    parser.add_argument("--source", type=Path, default=Path("assets/1024.png"))
    parser.add_argument("--out", type=Path, default=Path("assets/pixelmug-codex.icns"))
    parser.add_argument("--background", type=_hex_color, default=_hex_color("#FFFFFF"))
    args = parser.parse_args()

    base = make_base_icon(args.source, args.background)
    iconset = args.out.with_suffix(".iconset")
    save_iconset(base, iconset)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    save_icns(base, iconset, args.out)
    shutil.rmtree(iconset)
    print(f"Created {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
