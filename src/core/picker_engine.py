"""Picker engine: move selected PhotoItems from Folder A to Folder B,
and delete rejected PhotoItems (JPG + companion RAW).

Conflict handling for moves is delegated to the caller via a callback.
The callback receives the destination path and must return one of:
  "overwrite" | "skip" | "rename"
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ..models.photo_item import PhotoItem
from .file_ops import FileOpError, create_recycle_folder, move_file, safe_delete, unique_destination


ConflictChoice = str  # "overwrite" | "skip" | "rename"
ConflictResolver = Callable[[str], Optional[ConflictChoice]]


@dataclass
class PickReport:
    moved_jpg: int = 0
    moved_raw: int = 0
    missing_raw: int = 0
    deleted_jpg: int = 0
    deleted_raw: int = 0
    recycle_folder: Optional[str] = None
    skipped: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    multi_raw_warning: List[str] = field(default_factory=list)

    def as_text(self) -> str:
        lines = [
            "操作报告",
            "=" * 40,
        ]
        if self.moved_jpg or self.moved_raw:
            lines.append(f"移动到 B : {self.moved_jpg} 个 JPG, {self.moved_raw} 个 RAW")
        if self.deleted_jpg or self.deleted_raw:
            lines.append(f"移入临时文件夹 : {self.deleted_jpg} 个 JPG, {self.deleted_raw} 个 RAW")
            if self.recycle_folder:
                lines.append(f"  → {self.recycle_folder}")
        if self.missing_raw:
            lines.append(f"无伴随 RAW: {self.missing_raw}")
        if self.skipped:
            lines.append(f"跳过 (冲突): {len(self.skipped)}")
        if self.failed:
            lines.append(f"失败     : {len(self.failed)}")
        if self.failed:
            lines.append("--- 失败详情 ---")
            lines.extend(f"  - {n}" for n in self.failed)
        if self.skipped:
            lines.append("--- 跳过详情 ---")
            lines.extend(f"  - {n}" for n in self.skipped)
        return "\n".join(lines)


def _resolve_conflict(
    dst: str, resolver: Optional[ConflictResolver], report: PickReport
) -> tuple[bool, str]:
    """Return (should_write, final_dst). False = skip this file."""
    if not os.path.isfile(dst):
        return True, dst
    if resolver is None:
        # Default: skip conflicts silently.
        report.skipped.append(os.path.basename(dst))
        return False, dst
    choice = resolver(dst)
    if choice == "overwrite":
        return True, dst
    if choice == "rename":
        return True, unique_destination(dst)
    # anything else (including None) -> skip
    report.skipped.append(os.path.basename(dst))
    return False, dst


def pick_to_b(
    items: List[PhotoItem],
    folder_b: str,
    resolver: Optional[ConflictResolver] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> PickReport:
    """Move all selected PhotoItems into `folder_b`.

    `items`     - the PhotoItems the user ticked (PhotoItem.selected == True)
    `folder_b`  - target folder (must already exist; will be created if missing)
    `resolver`  - optional callback for destination conflicts
    `progress_cb` - optional callback (done, total) for progress UIs
    """
    report = PickReport()
    targets = [it for it in items if it.pick_status == "accepted"]
    total = len(targets)
    if total == 0:
        return report

    for idx, item in enumerate(targets, 1):
        # JPG
        if item.jpg_path and os.path.isfile(item.jpg_path):
            jpg_dst = os.path.join(folder_b, os.path.basename(item.jpg_path))
            write, jpg_dst = _resolve_conflict(jpg_dst, resolver, report)
            if write:
                try:
                    move_file(item.jpg_path, jpg_dst, overwrite=(jpg_dst == os.path.join(folder_b, os.path.basename(item.jpg_path))))
                    report.moved_jpg += 1
                except FileOpError as exc:
                    report.failed.append(f"{item.basename} (jpg): {exc}")
        else:
            # User might have deleted the source between scan and move
            report.failed.append(f"{item.basename}: jpg missing")

        # RAW (if any)
        if item.raw_path:
            if not os.path.isfile(item.raw_path):
                report.failed.append(f"{item.basename}: raw missing")
            else:
                raw_dst = os.path.join(folder_b, os.path.basename(item.raw_path))
                write, raw_dst = _resolve_conflict(raw_dst, resolver, report)
                if write:
                    try:
                        move_file(item.raw_path, raw_dst, overwrite=(raw_dst == os.path.join(folder_b, os.path.basename(item.raw_path))))
                        report.moved_raw += 1
                    except FileOpError as exc:
                        report.failed.append(f"{item.basename} (raw): {exc}")
        else:
            # No companion RAW - count as warning, JPG still moved
            report.missing_raw += 1

        if progress_cb:
            progress_cb(idx, total)
    return report


def delete_items(
    items: List[PhotoItem],
    target_folder: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> PickReport:
    """Move rejected JPG + companion RAW to a temporary _Orphaned_ folder
    inside `target_folder`, giving the user a chance to undo.

    The folder is named _Orphaned_YYYYMMDD_HHMMSS, created once per call.
    """
    report = PickReport()
    total = len(items)
    if total == 0:
        return report

    recycle_dir = create_recycle_folder(target_folder)
    report.recycle_folder = recycle_dir

    for idx, item in enumerate(items, 1):
        # Move JPG
        if item.jpg_path and os.path.isfile(item.jpg_path):
            try:
                dst = os.path.join(recycle_dir, os.path.basename(item.jpg_path))
                move_file(item.jpg_path, dst)
                report.deleted_jpg += 1
            except (FileOpError, OSError) as exc:
                report.failed.append(f"{item.basename} (jpg): {exc}")
        else:
            report.failed.append(f"{item.basename}: jpg missing")

        # Move RAW companion
        if item.raw_path:
            if os.path.isfile(item.raw_path):
                try:
                    dst = os.path.join(recycle_dir, os.path.basename(item.raw_path))
                    move_file(item.raw_path, dst)
                    report.deleted_raw += 1
                except (FileOpError, OSError) as exc:
                    report.failed.append(f"{item.basename} (raw): {exc}")
            else:
                report.failed.append(f"{item.basename}: raw missing")

        if progress_cb:
            progress_cb(idx, total)
    return report
