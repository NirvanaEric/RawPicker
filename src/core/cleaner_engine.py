"""Cleaner engine: remove orphan files safely (trash or permanent)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ..models.orphan_item import OrphanItem
from .file_ops import FileOpError, create_recycle_folder, move_file, safe_delete


@dataclass
class CleanReport:
    trashed: int = 0
    moved_to_recycle: int = 0
    permanently_deleted: int = 0
    failed: List[str] = field(default_factory=list)
    recycle_folder: Optional[str] = None

    def as_text(self) -> str:
        lines = [
            "Clean Report",
            "=" * 40,
            f"Recycle folder : {self.recycle_folder or '(n/a)'}",
            f"Moved to recycle : {self.moved_to_recycle}",
            f"Sent to trash    : {self.trashed}",
            f"Permanent delete : {self.permanently_deleted}",
            f"Failed           : {len(self.failed)}",
        ]
        if self.failed:
            lines.append("--- Failures ---")
            lines.extend(f"  - {n}" for n in self.failed)
        return "\n".join(lines)


def clean_orphans(
    orphans: List[OrphanItem],
    mode: str = "trash",
    target_folder: Optional[str] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> CleanReport:
    """Clean orphan files.

    mode='trash'      -> use send2trash (system recycle bin)
    mode='permanent'  -> os.remove, no recovery
    mode='recycle'    -> move to a _Orphaned_YYYYMMDD_HHMMSS folder inside
                         target_folder (fallback for systems where
                         send2trash isn't available).
    """
    report = CleanReport()
    targets = [o for o in orphans if o.selected]
    total = len(targets)
    if total == 0:
        return report

    if mode == "recycle":
        if not target_folder:
            raise ValueError("recycle mode requires target_folder")
        report.recycle_folder = create_recycle_folder(target_folder)

    for idx, orphan in enumerate(targets, 1):
        if not os.path.isfile(orphan.file_path):
            report.failed.append(f"{orphan.display_name}: missing")
            if progress_cb:
                progress_cb(idx, total)
            continue
        try:
            if mode == "recycle":
                dst = os.path.join(report.recycle_folder, orphan.display_name)  # type: ignore[arg-type]
                move_file(orphan.file_path, dst)
                report.moved_to_recycle += 1
            else:
                safe_delete(orphan.file_path, mode=mode)
                if mode == "trash":
                    report.trashed += 1
                else:
                    report.permanently_deleted += 1
        except FileOpError as exc:
            report.failed.append(f"{orphan.display_name}: {exc}")
        if progress_cb:
            progress_cb(idx, total)
    return report
