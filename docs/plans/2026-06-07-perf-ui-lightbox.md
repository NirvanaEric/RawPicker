# Perf + UI Redesign + Lightbox — Design & Plan

> Single session deliverable. 22 atomic commits. Tests stay green throughout.

## Goals
- 1500 张扫描 + 浏览顺滑 (PRD §11.1)
- 视觉对齐 Lightroom / Apple Photos
- 双击缩略图全屏 lightbox，完整快捷键支持

## Architecture

### Performance (Phase 2)
```
scan worker (thread) ──► queue ──► main thread poll
                                        │
                                        ▼
                                  apply_filter()
                                        │
                                        ▼
                              ThumbnailGrid.set_items()
                                        │
                                        ▼
                                _relayout_destroy_all()    ◄── debounced <Configure>
                                        │
                                        ▼
                             _create_cells_chunked()
                              30 cells / 16ms tick
                                        │
                                        ▼
                              cell.ensure_loaded() ──► image_cache.get_or_load()
```
Preview:
```
PreviewPanel.show(item) → schedule async decode on worker
                       → post CTkImage to queue
                       → main thread applies only if request_id matches
```

### UI redesign
- `Colors` palette: deep neutral + ACCENT yellow
- Global `corner_radius`: 12 (cards) / 8 (buttons) / 20 (pills)
- Typography: Segoe UI 12/13/14/18, 600 weight for numerics + selected
- Pill chips for badges, status, rating
- EXIF as 2-col key/value table
- Zero hard borders; use bg-color contrast

### Lightbox
- `ctk.CTkToplevel`, fullscreen, `grab_set()`
- Black canvas, fit-to-window default, `Z` toggles 1:1
- Top bar: filename + `12 / 1500` counter
- Right rail: EXIF
- Bottom: status pills + 5 stars + prev/next
- Reuse all keyboard handlers (A/X/P/U/Space/1-5/Esc/←/→)
- Image: async decode from JPG (full res), single-slot LRU (size 1)

## Risks (mitigated in code)
| Risk | Mitigation |
|------|-----------|
| EXIF orientation ignored | `ImageOps.exif_transpose` in `read_metadata` |
| Async race (A→B fast click) | `request_id` on each show; drop stale results |
| CTk no shadow/gradient | Color contrast + consistent radius only |
| Chunked create + selection | Defer `_refresh_selection` to last tick |
| Modal lightbox focus | `Toplevel.grab_set()` + `protocol("WM_DELETE_WINDOW")` |
| Font fallback | `ctk.CTkFont(family="Segoe UI")`; CTk falls back automatically |

## Plan (22 tasks, 5 phases)

### Phase 1 — Foundation (no visual change, all tests green)
- **T1** New `Colors` palette in `settings.py` (keep old names + add new)
- **T2** Add `read_metadata(path) -> (exif, lat, lon)` in `metadata_reader.py`
- **T3** Use `read_metadata` in `pick_tab._scan_worker`; add `apply_exif_transpose`
- **T4** Tests: `test_read_metadata` single open, orientation applied

### Phase 2 — Performance
- **T5** Split `image_cache` into `ThumbnailCache` + `PreviewCache` (separate caps)
- **T6** Debounce `<Configure>` in `ThumbnailGrid` (300ms)
- **T7** Skip relayout when column count unchanged
- **T8** Chunked cell creation: `_destroy_then_schedule_creates()` (30 per tick)
- **T9** `PreviewPanel.show()` async: worker thread + queue + request_id
- **T10** Preview decodes at `preview_max_height` (PIL `Image.thumbnail`)
- **T11** Tests: relayout col-count skip; preview async request_id

### Phase 3 — UI redesign
- **T12** Redesign `_ThumbCell`: pill badges, ACCENT border on select, hover bg
- **T13** Redesign `PreviewPanel`: black canvas, EXIF table, pill status buttons
- **T14** Redesign `Sidebar`: folder rows with status dot, segmented filter, big stats
- **T15** `PickBadge`/`RawBadge` → pill chips
- **T16** `RatingWidget` → 24px stars with hover
- **T17** `CTkTabview` + `dialogs/common.py` restyle (font, accent)

### Phase 4 — Lightbox
- **T18** `ui/lightbox.py`: `Lightbox` Toplevel with all the chrome
- **T19** Wire double-click in `_ThumbCell` → open lightbox
- **T20** Reuse keyboard handlers in lightbox; Esc closes
- **T21** Test: lightbox open/close, navigate, rating, pick

### Phase 5 — Verification
- **T22** Stress fixture 1000+ photos, perf measurement, full test pass, smoke

## Out of scope
- True RAW decode (rawpy)
- Video thumbnails
- macOS/Linux visual parity beyond CTk defaults
- Real-time perf profiler integration

## File changes
- New: `ui/lightbox.py`, `tests/test_lightbox.py`, `tests/test_metadata_single_read.py`, `tests/stress_1000.py`
- Modified: `config/settings.py`, `core/metadata_reader.py`, `utils/image_cache.py`, `ui/thumbnail_grid.py`, `ui/preview_panel.py`, `ui/sidebar.py`, `ui/pick_badge.py`, `ui/rating_widget.py`, `ui/dialogs/common.py`, `ui/pick_tab.py`, `ui/main_window.py`, `app.py`
