"""Path & template validation helpers."""
from __future__ import annotations

import os
import re
from typing import Optional

from ..config.settings import RAW_SET


def is_valid_folder(path: str) -> bool:
    """True if path is a non-empty string pointing at a real directory."""
    return bool(path) and os.path.isdir(path)


def normalize(path: str) -> str:
    """Return a canonical, comparable absolute path (no trailing slash)."""
    if not path:
        return ""
    return os.path.normpath(os.path.abspath(path))


_DISALLOWED = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_WIN = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])$", re.IGNORECASE)


def safe_filename(name: str, fallback: str = "file") -> str:
    """Strip Windows-illegal characters and reserved names."""
    if not name:
        return fallback
    name = _DISALLOWED.sub("_", name).strip().strip(".")
    if not name:
        return fallback
    if _RESERVED_WIN.match(name):
        return f"_{name}"
    return name


def is_raw_extension(ext: str) -> bool:
    return ext.lower().lstrip(".") in RAW_SET
