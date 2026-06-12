"""Folder scanners.

scan_for_picking:  JPG-anchored. Returns one PhotoItem per JPG, with the
                    companion RAW (if any) attached.
scan_for_cleaning:  basename-grouped. Returns (orphans, complete_pairs).
"""
from __future__ import annotations

import os
from typing import Dict, List, Tuple

from ..config.settings import JPG_SET, RAW_SET
from ..models.orphan_item import OrphanItem
from ..models.photo_item import PhotoItem


def _list_dir(folder: str) -> List[str]:
    """Yield absolute file paths directly under `folder` (no recursion)."""
    if not os.path.isdir(folder):
        return []
    out: List[str] = []
    try:
        for entry in os.listdir(folder):
            full = os.path.join(folder, entry)
            if os.path.isfile(full):
                out.append(full)
    except OSError:
        return []
    return out


def _split_basename_ext(path: str) -> Tuple[str, str]:
    base, ext = os.path.splitext(os.path.basename(path))
    return base, ext.lstrip(".").lower()


def scan_for_picking(folder_a: str) -> List[PhotoItem]:
    """Scan `folder_a`, return one PhotoItem per JPG.

    Each JPG is paired with the first matching RAW we find (case-insensitive).
    A separate `multi_raw_warnings` map is not needed in the return type - we
    keep the first match and call it a day; if the user has duplicates, the
    leftovers stay in Folder A and are discoverable via the cleaner.
    """
    if not os.path.isdir(folder_a):
        return []

    # First pass: bucket files by lowercase basename -> {ext: [paths]}
    buckets: Dict[str, Dict[str, List[str]]] = {}
    for path in _list_dir(folder_a):
        base, ext = _split_basename_ext(path)
        if ext not in JPG_SET and ext not in RAW_SET:
            continue
        buckets.setdefault(base, {}).setdefault(ext, []).append(path)

    # Second pass: build PhotoItem list, JPG-anchored
    items: List[PhotoItem] = []
    for base, by_ext in buckets.items():
        jpg_paths: List[str] = []
        for je in JPG_SET:
            jpg_paths.extend(by_ext.get(je, []))
        if not jpg_paths:
            # No JPG - this is an orphan RAW; not part of picking result.
            continue
        jpg_path = sorted(jpg_paths)[0]  # deterministic order
        jpg_ext = os.path.splitext(jpg_path)[1].lstrip(".").lower()

        raw_path: str | None = None
        raw_ext: str | None = None
        for rext in RAW_SET:
            candidates = by_ext.get(rext, [])
            if candidates:
                raw_path = sorted(candidates)[0]
                raw_ext = rext
                break

        items.append(PhotoItem(
            basename=base,
            folder=folder_a,
            jpg_path=jpg_path,
            jpg_ext=jpg_ext,
            raw_path=raw_path,
            raw_ext=raw_ext,
        ))
    items.sort(key=lambda p: p.basename)
    return items


def scan_for_cleaning(target_folder: str) -> Tuple[List[OrphanItem], List[PhotoItem]]:
    """Scan `target_folder` and return (orphans, complete_pairs).

    orphans:        RAW with no JPG, or JPG with no RAW
    complete_pairs: both files present (returned for the optional "review" view)
    """
    if not os.path.isdir(target_folder):
        return [], []

    buckets: Dict[str, Dict[str, List[str]]] = {}
    for path in _list_dir(target_folder):
        base, ext = _split_basename_ext(path)
        if ext not in JPG_SET and ext not in RAW_SET:
            continue
        buckets.setdefault(base, {}).setdefault(ext, []).append(path)

    orphans: List[OrphanItem] = []
    complete: List[PhotoItem] = []
    for base, by_ext in buckets.items():
        jpg_paths: List[str] = []
        for je in JPG_SET:
            jpg_paths.extend(by_ext.get(je, []))
        raw_paths: List[str] = []
        for re in RAW_SET:
            raw_paths.extend(by_ext.get(re, []))

        # For the "is this an orphan" check, we only care whether *any* file
        # of each kind exists - keep the first one for the UI.
        for p in jpg_paths:
            if not raw_paths:
                orphans.append(OrphanItem.from_path(p))
        for p in raw_paths:
            if not jpg_paths:
                orphans.append(OrphanItem.from_path(p))
        if jpg_paths and raw_paths:
            jpg_path = sorted(jpg_paths)[0]
            raw_path = sorted(raw_paths)[0]
            complete.append(PhotoItem(
                basename=base,
                folder=target_folder,
                jpg_path=jpg_path,
                jpg_ext=os.path.splitext(jpg_path)[1].lstrip(".").lower(),
                raw_path=raw_path,
                raw_ext=os.path.splitext(raw_path)[1].lstrip(".").lower(),
            ))
    orphans.sort(key=lambda o: o.file_path)
    complete.sort(key=lambda p: p.basename)
    return orphans, complete
