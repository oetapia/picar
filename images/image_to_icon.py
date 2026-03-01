#!/usr/bin/env python3
"""
Convert an image file to an icon and save it to icons.json.

Usage:
    python image_to_icon.py <image_path> <size> <icon_name> [--threshold N] [--invert] [--preview]

Examples:
    python image_to_icon.py images/star.png 8 star_8
    python image_to_icon.py images/arrow.png 16 arrow_16 --threshold 100
    python image_to_icon.py images/logo.png 24 my_logo --invert
    python image_to_icon.py images/test.png 8 test_8 --preview
"""

import argparse
import json
import os
import sys

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow is required. Install it with: pip install Pillow")
    sys.exit(1)

ICONS_JSON = os.path.join(os.path.dirname(__file__), 'icons.json')


def load_icons():
    if os.path.exists(ICONS_JSON):
        with open(ICONS_JSON) as f:
            return json.load(f)
    return {}


def save_icons(icons):
    with open(ICONS_JSON, 'w') as f:
        json.dump(icons, f, indent=2)


def convert(image_path, size, threshold=128, invert=False):
    img = Image.open(image_path)
    # Composite against white background to handle transparency before thresholding
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        img = img.convert('RGBA')
        background = Image.new('RGBA', img.size, (255, 255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    img = img.convert("L")  # grayscale
    img = img.resize((size, size), Image.LANCZOS)

    rows = []
    for y in range(size):
        value = 0
        for x in range(size):
            pixel = img.getpixel((x, y))
            is_on = (pixel < threshold) if not invert else (pixel >= threshold)
            if is_on:
                value |= 1 << (size - 1 - x)
        rows.append(value)
    return rows


def preview(rows, size, name):
    lines = []
    for i, row in enumerate(rows):
        bits = format(row, f"0{size}b")
        lines.append(f"    0b{bits},  # Row {i + 1}")
    lines[-1] = lines[-1].replace(",  #", "  #")
    print(f"{name} = [")
    for line in lines:
        print(line)
    print("]")


def main():
    parser = argparse.ArgumentParser(description="Convert image to icon and save to icons.json")
    parser.add_argument("image", help="Path to the input image")
    parser.add_argument("size", type=int, choices=[8, 16, 24, 32], help="Icon size (NxN pixels)")
    parser.add_argument("name", help="Icon name (e.g. star_16). Use this to reference it in code.")
    parser.add_argument("--threshold", type=int, default=128,
                        help="Brightness threshold 0-255 (default 128). Darker pixels become ON.")
    parser.add_argument("--invert", action="store_true",
                        help="Invert: light pixels become ON (for white-on-dark images)")
    parser.add_argument("--preview", action="store_true",
                        help="Print binary representation only, do not write to icons.json")
    args = parser.parse_args()

    rows = convert(args.image, args.size, args.threshold, args.invert)

    if args.preview:
        preview(rows, args.size, args.name)
    else:
        icons = load_icons()
        existed = args.name in icons
        icons[args.name] = rows
        save_icons(icons)
        verb = "Updated" if existed else "Added"
        print(f"{verb} '{args.name}' ({args.size}x{args.size}) in icons.json")


if __name__ == "__main__":
    main()
