"""Atomic file operations: conflict detection, retry, safe delete.

All functions in this module either succeed or raise FileOpError.
They never leave the filesystem in a half-moved state.
"""
from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from typing import Optional

# Lazy / optional import so unit tests can monkeypatch the name below.
try:
    from send2trash import send2trash as _send2trash
except ImportError:  # pragma: no cover
    _send2trash = None  # type: ignore[assignment]

# Re-export the function under a stable module-level name for patching.
send2trash = _send2trash


class FileOpError(Exception):
    pass


@dataclass
class MoveResult:
    src: str
    dst: str
    success: bool
    error: Optional[str] = None


def _retry(fn, *args, retries: int = 3, delay: float = 0.15, **kwargs):
    """Run fn(*args, **kwargs) up to `retries` times, retrying on OSError.

    Used to ride out transient Windows file-locking hiccups.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except OSError as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def move_file(src: str, dst: str, overwrite: bool = False) -> None:
    """Move a single file, creating parent directories as needed.

    Raises FileOpError on any failure.
    """
    if not os.path.isfile(src):
        raise FileOpError(f"source does not exist: {src}")
    parent = os.path.dirname(dst)
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError as exc:
            raise FileOpError(f"cannot create {parent}: {exc}") from exc
    if os.path.isfile(dst):
        if not overwrite:
            raise FileOpError(f"destination already exists: {dst}")
        try:
            os.remove(dst)
        except OSError as exc:
            raise FileOpError(f"cannot overwrite {dst}: {exc}") from exc
    try:
        _retry(shutil.move, src, dst)
    except (OSError, shutil.Error) as exc:
        raise FileOpError(f"move failed: {src} -> {dst}: {exc}") from exc


def unique_destination(dst: str) -> str:
    """If `dst` already exists, return `name_1.ext`, `name_2.ext`, ...

    Used by the "auto-rename on conflict" strategy.
    """
    if not os.path.exists(dst):
        return dst
    parent, name = os.path.split(dst)
    stem, ext = os.path.splitext(name)
    i = 1
    while True:
        candidate = os.path.join(parent, f"{stem}_{i}{ext}")
        if not os.path.exists(candidate):
            return candidate
        i += 1


def safe_delete(path: str, mode: str = "trash") -> None:
    """Delete a file.

    mode='trash'      -> use send2trash (recoverable via OS recycle bin)
    mode='permanent'  -> os.remove, no recovery
    """
    if not os.path.isfile(path):
        return
    if mode == "trash":
        if send2trash is None:
            raise FileOpError("send2trash not available")
        try:
            send2trash(path)
        except Exception as exc:
            raise FileOpError(f"trash failed for {path}: {exc}") from exc
    else:
        try:
            os.remove(path)
        except OSError as exc:
            raise FileOpError(f"delete failed for {path}: {exc}") from exc


def create_recycle_folder(target_folder: str) -> str:
    """Create a unique _Orphaned_YYYYMMDD_HHMMSS subfolder inside `target_folder`.

    Returns the created folder path. Raises FileOpError on failure.
    """
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    recycle = os.path.join(target_folder, f"_Orphaned_{ts}")
    try:
        os.makedirs(recycle, exist_ok=True)
    except OSError as exc:
        raise FileOpError(f"cannot create recycle folder {recycle}: {exc}") from exc
    return recycle
