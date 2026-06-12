"""Application controller: wires the UI to the engines and persists config."""
from __future__ import annotations

import os
from typing import List, Optional

import customtkinter as ctk

from .config.settings import AppConfig, Colors
from .core.cleaner_engine import CleanReport, clean_orphans
from .core.picker_engine import PickReport, pick_to_b, delete_items
from .models.orphan_item import OrphanItem
from .models.photo_item import PhotoItem
from .ui.dialogs.common import ConfirmDialog, ConflictDialog, ReportDialog
from .ui.lightbox import Lightbox
from .ui.main_window import MainWindow
from .utils.config_store import load_config, save_config
from .utils.image_cache import ImageCache, PreviewCache
from .utils.thumbnail_loader import ThumbnailLoader

# Dark theme by default — professional photo-editing ergonomics.
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App:
    """Glue layer between UI tabs and the core engines."""

    def __init__(self) -> None:
        self.config: AppConfig = load_config()
        # The ThumbnailLoader does background decoding; cells just
        # call loader.submit() and install the result asynchronously.
        self.loader: ThumbnailLoader = ThumbnailLoader(num_workers=None, capacity=1024)
        # Backwards-compat shim for any direct cache callers.
        self.cache: ImageCache = ImageCache(capacity=1024)
        self.preview_cache: PreviewCache = PreviewCache(capacity=4)
        self._lightbox: Optional[Lightbox] = None
        self.window = MainWindow(
            self.config, self.loader, self.preview_cache,
            on_pick_to_b=self.handle_pick_to_b,
            on_recent_pair=self.handle_recent_pair,
            on_show_message=self.show_message,
            on_jump_to_clean=self.jump_to_clean,
            on_clean=self.handle_clean,
            on_rename_done=self.handle_rename_done,
            on_open_lightbox=self.open_lightbox,
        )
        # Restore last folders into the UI
        if self.config.folder_a or self.config.folder_b:
            self.window.pick_tab().set_folders(self.config.folder_a, self.config.folder_b)

    # -- main loop ---------------------------------------------------------
    def run(self) -> None:
        try:
            self.window.mainloop()
        finally:
            save_config(self.config)

    # -- message dialogs ---------------------------------------------------
    def show_message(self, title: str, body: str) -> None:
        ReportDialog(self.window, title=title, body=body)

    # -- batch workflow (move accepted → B, delete rejected) ----------------
    def handle_pick_to_b(self, items: List[PhotoItem]) -> None:
        """Execute the batch operation: move accepted items to B, delete rejected."""
        if not items:
            self.show_message("执行操作", "没有标记的照片")
            return
        # Separate by status
        accepted = [it for it in items if it.pick_status == "accepted"]
        rejected = [it for it in items if it.pick_status == "rejected"]
        if not accepted and not rejected:
            self.show_message("执行操作", "没有需要操作的照片（仅有 Pending 状态）")
            return
        # Validate B folder for accepted items
        if accepted:
            folder_b = self.window.pick_tab().get_folders()[1]
            if not folder_b or not os.path.isdir(folder_b):
                self.show_message("执行操作", f"Folder B 无效: {folder_b}")
                return
        # Build confirmation message
        parts = []
        if accepted:
            raw_count = sum(1 for it in accepted if it.has_raw)
            parts.append(f"移动 {len(accepted)} 个 JPG" +
                        (f" + {raw_count} 个 RAW" if raw_count else "") +
                        f"\n→ 目标: {folder_b}")
        if rejected:
            raw_count = sum(1 for it in rejected if it.has_raw)
            parts.append(f"删除 {len(rejected)} 个 JPG" +
                        (f" + {raw_count} 个 RAW" if raw_count else ""))
        pending = len(items) - len(accepted) - len(rejected)
        if pending:
            parts.append(f"保留 {pending} 个 (Pending)")
        msg = "\n\n".join(parts) + "\n\n是否继续?"
        has_reject = bool(rejected)
        dlg = ConfirmDialog(self.window, title="确认操作", message=msg,
                            confirm_text="执行", danger=has_reject)
        self.window.wait_window(dlg)
        if not dlg.get_result():
            return
        # Execute moves
        report = PickReport()
        if accepted:
            move_report = pick_to_b(accepted, folder_b, resolver=self.resolve_conflict)
            report.moved_jpg = move_report.moved_jpg
            report.moved_raw = move_report.moved_raw
            report.missing_raw = move_report.missing_raw
            report.skipped.extend(move_report.skipped)
            report.failed.extend(move_report.failed)
        # Execute deletes
        if rejected:
            folder_a = self.window.pick_tab().get_folders()[0]
            del_report = delete_items(rejected, target_folder=folder_a)
            report.deleted_jpg = del_report.deleted_jpg
            report.deleted_raw = del_report.deleted_raw
            report.recycle_folder = del_report.recycle_folder
            report.failed.extend(del_report.failed)
        self.show_message("操作完成", report.as_text())
        # Refresh pick tab
        self.window.pick_tab().scan()

    def resolve_conflict(self, dst: str) -> Optional[str]:
        dlg = ConflictDialog(self.window, dst=dst)
        self.window.wait_window(dlg)
        return dlg.get_result()

    def handle_recent_pair(self, a: str, b: str) -> None:
        if a and b:
            self.config.remember_pair(a, b)

    def jump_to_clean(self, folder: str) -> None:
        self.window.select_tab("清理 (Ctrl+2)")
        if folder and os.path.isdir(folder):
            self.window.clean_tab()._folder_var.set(folder)  # noqa: SLF001

    # -- clean workflow ----------------------------------------------------
    def handle_clean(self, orphans: List[OrphanItem], mode: str,
                     target_folder: Optional[str]) -> None:
        total = sum(o.size_mb for o in orphans)
        msg = (f"将{'永久删除' if mode == 'permanent' else '清理'} "
               f"{len(orphans)} 个文件，共 {total:.1f} MB")
        if mode == "permanent":
            msg += "\n\n⚠ 此操作不可恢复，是否继续?"
        else:
            msg += "\n\n是否继续?"
        dlg = ConfirmDialog(self.window, title="确认清理", message=msg,
                            confirm_text="执行", danger=mode == "permanent")
        self.window.wait_window(dlg)
        if not dlg.get_result():
            return
        report: CleanReport = clean_orphans(orphans, mode=mode, target_folder=target_folder)
        self.show_message("清理完成", report.as_text())
        # Re-scan
        self.window.clean_tab().scan()

    # -- rename workflow ---------------------------------------------------
    def handle_rename_done(self) -> None:
        # The rename tab may want to know; we trigger its internal refresh by
        # re-scanning the pick tab too. Cheapest: just tell pick tab to re-scan
        # so any cross-tab state stays consistent.
        pass

    # -- lightbox ---------------------------------------------------------
    def open_lightbox(self, item: PhotoItem) -> None:
        """Open (or refocus) the lightbox on `item`, navigating from the
        currently-filtered grid."""
        pick = self.window.pick_tab()
        items = pick._filtered_items()  # noqa: SLF001
        try:
            index = items.index(item)
        except ValueError:
            items = [item]
            index = 0
        if self._lightbox is not None and self._lightbox.winfo_exists():
            try:
                self._lightbox.destroy()
            except Exception:
                pass
        self._lightbox = Lightbox(
            self.window,
            items=items, index=index, cache=self.preview_cache,
            on_close=self._on_lightbox_close,
            on_pick_change=self._on_lightbox_pick,
            on_rating_change=self._on_lightbox_rating,
        )

    def _on_lightbox_close(self) -> None:
        self._lightbox = None
        # Refresh the grid so badge / cell visuals reflect any state changes.
        try:
            self.window.pick_tab().refresh()
        except Exception:
            pass

    def _on_lightbox_pick(self, item: PhotoItem, status: str) -> None:
        item.pick_status = status
        # Update the pick tab so the badge in the cell flips immediately.
        pick = self.window.pick_tab()
        if item in pick.current_items():
            pick.refresh()
        # Keep the lightbox in sync if it's still open
        if self._lightbox is not None and self._lightbox.winfo_exists():
            self._lightbox._show_current()  # noqa: SLF001

    def _on_lightbox_rating(self, item: PhotoItem, value: int) -> None:
        item.rating = value
        pick = self.window.pick_tab()
        if item in pick.current_items():
            pick.refresh()
        if self._lightbox is not None and self._lightbox.winfo_exists():
            self._lightbox._show_current()  # noqa: SLF001
