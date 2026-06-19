"""Persist AppConfig to JSON on disk."""
from __future__ import annotations

import json
import os
import shutil
from typing import Optional

from ..config.settings import AppConfig, default_config_path

_OLD_NAMES = ["RawPickerPro"]  # migrated appdata folder names


def _migrate_old_config(cfg_path: str) -> None:
    """Migrate settings from previous appdata folder names."""
    if os.path.isfile(cfg_path):
        return
    base = os.path.dirname(cfg_path)
    for old in _OLD_NAMES:
        old_path = os.path.join(os.path.dirname(base), old, "settings.json")
        if os.path.isfile(old_path):
            os.makedirs(base, exist_ok=True)
            shutil.copy2(old_path, cfg_path)
            return


def load_config(path: Optional[str] = None) -> AppConfig:
    cfg_path = path or str(default_config_path())
    _migrate_old_config(cfg_path)
    if not os.path.isfile(cfg_path):
        return AppConfig()
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AppConfig.from_dict(data)
    except (OSError, ValueError, json.JSONDecodeError):
        return AppConfig()


def save_config(cfg: AppConfig, path: Optional[str] = None) -> None:
    cfg_path = path or str(default_config_path())
    parent = os.path.dirname(cfg_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = cfg_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg.to_dict(), f, indent=2, ensure_ascii=False)
    os.replace(tmp, cfg_path)
