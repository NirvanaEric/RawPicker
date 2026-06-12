"""Application constants, default settings, and color palette."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple


RAW_FORMATS: List[str] = [
    "nef", "cr2", "cr3", "arw", "raf", "orf", "dng", "rw2", "pef", "x3f",
    "srw", "nrw", "erf", "kdc", "k25", "mef", "dcr", "mos", "iiq", "rwl",
    "gpr", "3fr", "crw", "sr2", "srf", "bay", "cs1", "fff", "mdc", "mrw",
    "qtk", "raw", "rwz", "sti", "tif", "tiff",
]

JPG_FORMATS: List[str] = ["jpg", "jpeg"]

# Build a frozenset for O(1) membership tests in hot loops.
RAW_SET = frozenset(RAW_FORMATS)
JPG_SET = frozenset(JPG_FORMATS)


# -- Color palette (Apple Photos light) ------------------------------------
class Colors:
    # Surfaces
    BG              = "#FFFFFF"   # window background, primary surface
    BG_BASE         = BG          # legacy alias
    SURFACE         = "#F2F2F7"   # alternating rows, sidebars
    BG_LIGHT        = SURFACE     # legacy alias
    SURFACE_RAISED  = "#FFFFFF"   # cards (lifted by subtle shadow)
    BG_DARK         = SURFACE     # legacy alias
    BG_DARKER       = BG          # legacy alias

    # Borders
    BORDER          = "#D1D1D6"   # 1px hairlines
    BORDER_SUBTLE   = "#E5E5EA"   # very light divider

    # Text
    TEXT            = "#1C1C1E"   # primary
    TEXT_DIM        = "#8E8E93"   # secondary / metadata
    TEXT_DISABLED   = "#C7C7CC"

    # Accent (Apple system blue)
    ACCENT          = "#0A84FF"
    ACCENT_SOFT     = "#E5F0FF"   # 8% blue tint for selected-cell bg
    PRIMARY         = ACCENT      # legacy alias
    PICK_ACCENT     = ACCENT      # legacy alias
    INFO            = ACCENT      # legacy alias

    # Status
    ACCEPTED        = "#34C759"   # green
    REJECTED        = "#FF3B30"   # red
    PENDING         = "#8E8E93"   # grey
    WARNING         = "#FF9F0A"   # amber
    HIGH_RATING     = "#FFCC00"   # star fill (yellow)

    # Lightbox image canvas (kept dark for photography evaluation)
    LIGHTBOX_BG     = "#0E0E10"


# -- Application configuration ---------------------------------------------
@dataclass
class AppConfig:
    folder_a: str = ""
    folder_b: str = ""
    raw_formats: List[str] = field(default_factory=lambda: list(RAW_FORMATS))
    jpg_formats: List[str] = field(default_factory=lambda: list(JPG_FORMATS))
    thumbnail_size: int = 160
    preview_max_height: int = 400
    theme: str = "light"               # "dark" | "light"
    delete_mode: str = "trash"         # "trash" | "permanent"
    recent_paths: List[Tuple[str, str]] = field(default_factory=list)  # (A, B) pairs
    xmp_writeback: bool = False
    max_recent: int = 5

    # Recent-paths helpers
    def remember_pair(self, folder_a: str, folder_b: str) -> None:
        pair = (folder_a, folder_b)
        if pair in self.recent_paths:
            self.recent_paths.remove(pair)
        self.recent_paths.insert(0, pair)
        del self.recent_paths[self.max_recent:]

    def to_dict(self) -> dict:
        return {
            "folder_a": self.folder_a,
            "folder_b": self.folder_b,
            "raw_formats": list(self.raw_formats),
            "jpg_formats": list(self.jpg_formats),
            "thumbnail_size": self.thumbnail_size,
            "preview_max_height": self.preview_max_height,
            "theme": self.theme,
            "delete_mode": self.delete_mode,
            "recent_paths": [list(p) for p in self.recent_paths],
            "xmp_writeback": self.xmp_writeback,
            "max_recent": self.max_recent,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        cfg = cls()
        cfg.folder_a = data.get("folder_a", "")
        cfg.folder_b = data.get("folder_b", "")
        cfg.raw_formats = data.get("raw_formats", list(RAW_FORMATS))
        cfg.jpg_formats = data.get("jpg_formats", list(JPG_FORMATS))
        cfg.thumbnail_size = int(data.get("thumbnail_size", 160))
        cfg.preview_max_height = int(data.get("preview_max_height", 400))
        cfg.theme = data.get("theme", "dark")
        cfg.delete_mode = data.get("delete_mode", "trash")
        cfg.recent_paths = [tuple(p) for p in data.get("recent_paths", [])]
        cfg.xmp_writeback = bool(data.get("xmp_writeback", False))
        cfg.max_recent = int(data.get("max_recent", 5))
        return cfg


# Default location for persisted settings: %APPDATA%/RawPickerPro/settings.json
def default_config_path() -> Path:
    import os
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "RawPickerPro" / "settings.json"


PICK_STATES = ("accepted", "rejected", "pending")
