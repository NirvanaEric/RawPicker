"""Helper: create a folder of synthetic JPG+RAW fixtures for tests.

Generates minimal but valid JPGs (using Pillow) and empty .nef / .cr2 files
to simulate the on-disk layout a real photographer would have.
"""
from __future__ import annotations

import os
from PIL import Image, ImageDraw


def make_jpg(path: str, color: tuple[int, int, int] = (200, 200, 200),
             text: str = "") -> None:
    """Write a 320x240 JPG with a coloured background and optional text."""
    img = Image.new("RGB", (320, 240), color)
    if text:
        d = ImageDraw.Draw(img)
        d.text((10, 10), text, fill=(0, 0, 0))
    img.save(path, "JPEG", quality=85)


def touch(path: str) -> None:
    """Create an empty file (used to fake a RAW body)."""
    with open(path, "wb") as f:
        f.write(b"\x00")


def make_fixture_set(folder: str) -> dict:
    """Create a folder layout and return the file paths grouped by role.

    Layout:
        folder/
          pair_01.jpg  + pair_01.nef      (complete pair)
          pair_02.jpg  + pair_02.cr2      (complete pair, alt RAW ext)
          pair_03.jpg                     (JPG with no companion RAW)
          orphan_raw_01.dng               (orphan RAW)
          orphan_raw_02.arw               (orphan RAW)
          orphan_jpg_01.jpg               (orphan JPG)
          subdir/                          (should be ignored - non-recursive)
    """
    os.makedirs(folder, exist_ok=True)
    files = {}
    files["pair_01_jpg"] = os.path.join(folder, "pair_01.jpg")
    files["pair_01_raw"] = os.path.join(folder, "pair_01.nef")
    files["pair_02_jpg"] = os.path.join(folder, "pair_02.jpg")
    files["pair_02_raw"] = os.path.join(folder, "pair_02.cr2")
    files["pair_03_jpg"] = os.path.join(folder, "pair_03.jpg")
    files["orphan_raw_01"] = os.path.join(folder, "orphan_raw_01.dng")
    files["orphan_raw_02"] = os.path.join(folder, "orphan_raw_02.arw")
    files["orphan_jpg_01"] = os.path.join(folder, "orphan_jpg_01.jpg")

    for jp in (files["pair_01_jpg"], files["pair_02_jpg"],
               files["pair_03_jpg"], files["orphan_jpg_01"]):
        make_jpg(jp)
    for r in (files["pair_01_raw"], files["pair_02_raw"],
              files["orphan_raw_01"], files["orphan_raw_02"]):
        touch(r)
    # Make a subdir to confirm scanner doesn't recurse
    sub = os.path.join(folder, "subdir")
    os.makedirs(sub, exist_ok=True)
    make_jpg(os.path.join(sub, "hidden.jpg"))
    touch(os.path.join(sub, "hidden.nef"))

    return files
