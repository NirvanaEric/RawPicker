"""Renamer engine: template-based batch rename for picking/cleaning/rename tabs.

Supported variables:
  {basename}      - original basename (no extension)
  {seq}           - 1-based sequence number across the input
  {seq:03d}       - zero-padded; any printf width works: {seq:04d}, {seq:05d}
  {rating}        - PhotoItem.rating; empty string when 0
  {date}          - EXIF DateTimeOriginal (YYYYMMDD) or file mtime
  {camera}        - EXIF Model

If a PhotoItem is passed in, the engine keeps RAW and JPG in sync: both files
get renamed to `<new>.<jpg_ext>` and `<new>.<raw_ext>`.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable, List, Optional, Sequence

from ..models.photo_item import PhotoItem
from .file_ops import FileOpError, move_file


_VAR_RE = re.compile(r"\{([a-zA-Z_]+)(?::([^}]+))?\}")


@dataclass
class RenameResult:
    renamed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    def as_text(self) -> str:
        lines = [
            "Rename Report",
            "=" * 40,
            f"Renamed : {len(self.renamed)}",
            f"Skipped : {len(self.skipped)}",
            f"Failed  : {len(self.failed)}",
        ]
        if self.failed:
            lines.append("--- Failures ---")
            lines.extend(f"  - {n}" for n in self.failed)
        return "\n".join(lines)


# -- Template helpers --------------------------------------------------------

def _format_seq(value: int, spec: str) -> str:
    """Apply a printf-style width spec like '03d' or '04d'."""
    if not spec:
        return str(value)
    m = re.match(r"^0?(\d+)d$", spec.strip())
    if not m:
        return str(value)
    width = int(m.group(1))
    return f"{value:0{width}d}"


def _format_date(exif: dict, fallback_mtime: float) -> str:
    raw = exif.get("DateTimeOriginal") or exif.get("DateTime")
    if raw:
        # EXIF format: "YYYY:MM:DD HH:MM:SS"
        try:
            dt = datetime.strptime(str(raw)[:19], "%Y:%m:%d %H:%M:%S")
            return dt.strftime("%Y%m%d")
        except (ValueError, TypeError):
            pass
    return datetime.fromtimestamp(fallback_mtime).strftime("%Y%m%d")


def _format_camera(exif: dict) -> str:
    make = str(exif.get("Make", "")).strip()
    model = str(exif.get("Model", "")).strip()
    cam = model or make
    if make and model and model.startswith(make):
        cam = model
    # sanitize so the result is filename-safe
    return re.sub(r"[^\w.\-]+", "_", cam)


def _eval_template(
    template: str,
    item: PhotoItem,
    seq: int,
) -> str:
    """Expand template variables for a single item."""
    def repl(m: re.Match) -> str:
        name = m.group(1).lower()
        spec = m.group(2) or ""
        if name == "basename":
            return item.basename
        if name == "seq":
            return _format_seq(seq, spec)
        if name == "rating":
            return str(item.rating) if item.rating else ""
        if name == "date":
            mtime = os.path.getmtime(item.jpg_path) if item.jpg_path and os.path.isfile(item.jpg_path) else 0
            return _format_date(item.exif, mtime)
        if name == "camera":
            return _format_camera(item.exif)
        return m.group(0)  # unknown var left untouched
    expanded = _VAR_RE.sub(repl, template)
    # Final filename safety scrub
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", expanded).strip() or item.basename


def preview_renames(
    items: Sequence[PhotoItem],
    template: str,
    limit: int = 5,
) -> List[tuple[str, str]]:
    """Return up to `limit` (old_name, new_name) pairs for the preview UI."""
    out: List[tuple[str, str]] = []
    for i, it in enumerate(items[:limit], 1):
        new_base = _eval_template(template, it, i)
        if it.jpg_path:
            old = os.path.basename(it.jpg_path)
            new = f"{new_base}.{it.jpg_ext}"
        elif it.raw_path:
            old = os.path.basename(it.raw_path)
            new = f"{new_base}.{it.raw_ext or ''}"
        else:
            old, new = it.basename, new_base
        out.append((old, new))
    return out


def rename_items(
    items: Sequence[PhotoItem],
    template: str,
    folder: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> RenameResult:
    """Rename JPGs and (when present) companion RAWs in lockstep.

    Both files are renamed to `<new>.<jpg_ext>` and `<new>.<raw_ext>`.
    """
    result = RenameResult()
    total = len(items)
    for i, item in enumerate(items, 1):
        new_base = _eval_template(template, item, i)
        try:
            if item.jpg_path and os.path.isfile(item.jpg_path):
                jpg_dst = os.path.join(folder, f"{new_base}.{item.jpg_ext}")
                if os.path.abspath(item.jpg_path) == os.path.abspath(jpg_dst):
                    result.skipped.append(item.basename)
                    if progress_cb:
                        progress_cb(i, total)
                    continue
                move_file(item.jpg_path, jpg_dst)
                result.renamed.append(os.path.basename(jpg_dst))
            if item.raw_path and os.path.isfile(item.raw_path):
                raw_dst = os.path.join(folder, f"{new_base}.{item.raw_ext}")
                if os.path.abspath(item.raw_path) == os.path.abspath(raw_dst):
                    continue
                move_file(item.raw_path, raw_dst)
        except FileOpError as exc:
            result.failed.append(f"{item.basename}: {exc}")
        if progress_cb:
            progress_cb(i, total)
    return result
