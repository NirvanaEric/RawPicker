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


# -- Color palette (professional dark theme) --------------------------------
# Design principles (researched from Lightroom, Capture One, Darktable):
#   1. NEUTRAL GRAY — UI must be chromatically neutral (R≈G≈B) so it does
#      NOT distort the photographer's color perception of the photo.
#   2. PHOTO IS THE STAR — the image area must always be the *brightest*
#      element on screen. Everything else recedes.
#   3. NO PURE BLACK/WHITE — pure #000 causes halation (eye strain); pure
#      #FFF competes with the photo. Use off-whites and near-blacks.
#   4. ELEVATION = LUMINANCE — higher surfaces are lighter, not shadowed.
#      Shadows are invisible on dark backgrounds; depth comes from value.
#   5. COLOR = FUNCTION ONLY — blue for selection/interaction, green for
#      accepted, red for rejected. UI chrome stays grayscale.
#   6. COMFORT FOR LONG SESSIONS — ~8-12:1 primary text contrast is
#      *plenty*. Higher ratios cause eye fatigue (halation).
# Reference: Adobe Spectrum, Apple HIG, Darktable LCH palette, Material.
class Colors:
    # Surfaces (luminance hierarchy: higher number = lighter = closer)
    BG              = "#2C2C2C"   # root window  (Spectrum gray-100)
    SURFACE         = "#363636"   # sidebar, panels
    SURFACE_RAISED  = "#404040"   # cards, elevated elements
    SURFACE_DEEP    = "#262626"   # behind panels, section headers

    # Borders — subtle; avoid hard lines that create visual noise
    BORDER          = "#484848"   # 1px hairline
    BORDER_SUBTLE   = "#3A3A3A"   # very light divider

    # Text — three-tier hierarchy, off-white only
    TEXT            = "#E0E0E0"   # primary   (~9:1 on BG)
    TEXT_DIM        = "#98989D"   # secondary (~5:1 on BG)
    TEXT_DISABLED   = "#636366"  # muted     (~2.5:1, intentional)

    # Accent (reserved for interactive elements only)
    ACCENT          = "#0A84FF"
    ACCENT_SOFT     = "#1A2A44"  # blue tint for selected-cell bg
    ACCENT_HOVER    = "#409CFF"

    # Status — semi-saturated, used sparingly for meaning only
    ACCEPTED        = "#30D158"
    ACCEPTED_SOFT   = "#1A3A22"
    REJECTED        = "#FF453A"
    REJECTED_SOFT   = "#3A1A1A"
    PENDING         = "#8E8E93"
    WARNING         = "#FF9F0A"
    HIGH_RATING     = "#FFD60A"

    # Lightbox — darker stage for focused evaluation
    LIGHTBOX_BG     = "#0E0E10"

    # --- Light theme (Apple Photos warm) ---
    class Light:
        class Deep:
            BG              = "#F5F5F7"
            SURFACE         = "#FFFFFF"
            SURFACE_RAISED  = "#FFFFFF"
            SURFACE_DEEP    = "#EBEBF0"
            BORDER          = "#D2D2D7"
            BORDER_SUBTLE   = "#E5E5EA"
            TEXT            = "#1D1D1F"
            TEXT_DIM        = "#6E6E73"
            TEXT_DISABLED   = "#C7C7CC"
            ACCENT          = "#0A84FF"
            ACCENT_SOFT     = "#E5F0FF"
            ACCENT_HOVER    = "#006DDB"
            ACCEPTED        = "#34C759"
            ACCEPTED_SOFT   = "#E8F8ED"
            REJECTED        = "#FF3B30"
            REJECTED_SOFT   = "#FFECEB"
            PENDING         = "#8E8E93"
            WARNING         = "#FF9F0A"
            HIGH_RATING     = "#FFCC00"
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
    theme: str = "dark"                # "dark" | "light"
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


# Default location for persisted settings: %APPDATA%/RawPicker/settings.json
def default_config_path() -> Path:
    import os
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "RawPicker" / "settings.json"


PICK_STATES = ("accepted", "rejected", "pending")
