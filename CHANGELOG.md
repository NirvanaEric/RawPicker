# Changelog

## [Unreleased]

### Added
- Screenshots in README (main_screen.jpg, lightbox.jpg)
- CHANGELOG.md
- LICENSE (GPL-3.0)

### Changed
- README restructured to yiyin-style: features, usage, screenshots, shortcuts, supported formats, ending, donate
- README split into Chinese (README.md) and English (readme_en.md)
- Software name changed from "RawPicker Pro" to "RawPicker"

## [0.1.0] - 2026-06-12

### Added
- Lightbox zoom + pan: 5-level stepped zoom (0.25x-4x), Z toggles fit/1:1, tk.Canvas with scan_mark/scan_dragto
- Adjacent image pre-decode in lightbox for instant navigation
- App icon (CustomTkinter-style blue square, icon.ico)

### Performance
- BILINEAR resampling for thumbnails (3-5x faster than LANCZOS)
- Unified PIL cache between grid and lightbox, removed redundant `_image_cache`
- Background thread pool decode (6 workers)
- Scroll-direction prediction in thumbnail grid

### Fixed
- UI freeze on batch operations: threaded pick_to_b, clean_orphans, rename_items
- ReportDialog grab_set() freeze: detached from _DialogShell, uses CTkToplevel + wait_window()
- TclError in preview_panel: removed `image=None` from CTkLabel.configure()

## [0.0.1] - 2026-06-10

### Added
- Dark professional theme (Lightroom/Capture One inspired neutral-gray palette)
- UI components: thumbnail grid with virtual cells, sidebar cards/filter/stats, preview panel, lightbox
- Pick workflow: scan JPGs, mark A/D, batch move/delete
- Clean workflow: find orphan RAW/JPG files
- Rename workflow: batch rename with template ({basename}, {seq}, {rating}, {date}, {camera})
- Map view: GPS-tagged photos on OpenStreetMap
- Keyboard-first navigation
- PyInstaller packaging: single-file Windows exe
