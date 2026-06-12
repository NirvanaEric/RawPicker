# Preview Panel + Lightbox Fixes Plan

## Problem Analysis

Three issues reported:

### Issue 1: Preview panel width changes with photo
- `preview_panel.py:53` creates `_image_label` with `width=380, height=max_h`
- When `configure(image=ctk_img)` is called, the label resizes to fit the CTkImage's native dimensions
- The grid column (weight=0, minsize=400) allows the label to push the column wider
- Fix: wrap the image label in a frame with `pack_propagate(False)` to enforce fixed size

### Issue 2: Lightbox image doesn't fit window, no zoom
- `_refresh_image()` at line 292 is a **no-op** — it does nothing
- `_decode_worker` creates CTkImage at a fixed size; on window resize, the image stays the same size
- `_toggle_zoom()` flips the mode string but `_refresh_image()` is empty so nothing happens
- Fix: store the PIL image from decode, re-create CTkImage on `<Configure>` and zoom toggle

### Issue 3: CTkLabel warning "Given image is not CTkImage but \<class 'str'\>"
- CTkLabel._check_image_type (customtkinter source) fires this when image is not CTkImage
- 5 occurrences pass `image=""` (empty string) to clear the label — strings trigger the warning
- Fix: use `image=None` instead of `image=""` at all 5 call sites

---

## Task 1: Fix CTkLabel warning (trivial)

**Files:** `src/ui/preview_panel.py`, `src/ui/lightbox.py`

Replace all `image=""` with `image=None` in configure calls:
- `preview_panel.py:141` — `(未选择)` placeholder
- `preview_panel.py:153` — `加载中…` loading text
- `preview_panel.py:199` — fallback text on decode error
- `lightbox.py:253` — `(无照片)` placeholder
- `lightbox.py:260` — `加载中…` loading text

---

## Task 2: Fix preview panel fixed width

**Files:** `src/ui/preview_panel.py`

Wrap `_image_label` in a CTkFrame with fixed height and `pack_propagate(False)`:
- Create `self._img_frame = ctk.CTkFrame(self, fg_color=Colors.LIGHTBOX_BG, corner_radius=8, height=self._max_h)`
- `self._img_frame.pack(padx=12, pady=(12, 8), fill="x")`
- `self._img_frame.pack_propagate(False)` — prevents the frame from shrinking/growing
- `self._image_label = ctk.CTkLabel(self._img_frame, text="(未选择)", fg_color=Colors.LIGHTBOX_BG, ...)`
- `self._image_label.pack(fill="both", expand=True)` — label fills the fixed frame
- Image is centered by default in CTkLabel (anchor="center")

---

## Task 3: Fix lightbox image fit + zoom

**Files:** `src/ui/lightbox.py`

### 3a: Store PIL image from decode
- Add `self._pil_image: Optional[Image.Image] = None` to `__init__`
- In `_decode_worker`: decode to PIL, store as `self._pil_image`, then create CTkImage at fit size
- The decode worker needs to return the PIL image, not just CTkImage

### 3b: Implement `_refresh_image()`
- If `_pil_image` is None, return (no image loaded yet)
- Get current label dimensions: `iw = self._image_label.winfo_width()`, `ih = self._image_label.winfo_height()`
- If zoom == "fit": compute bounding box preserving aspect ratio
- If zoom == "1:1": use full PIL image dimensions (no scaling)
- Create CTkImage from the (possibly scaled) PIL image
- `self._image_label.configure(image=ctk_img, text="")`

### 3c: Wire `<Configure>` properly
- The existing `self._image_label.bind("<Configure>", lambda _e: self._refresh_image())` is already there
- Now it will actually do something

### 3d: Import PIL.Image in lightbox
- Add `from PIL import Image as PILImage` at the top

---

## Verification

```bash
uv run python -m pytest -q --ignore=tests/test_scale.py   # 41+ tests pass
uv run python smoke.py                                     # 4 workflows pass
```

Manual checks:
- Preview panel width stays constant when switching between landscape/portrait photos
- Lightbox: image fills the window, Z toggles between fit and 1:1
- No CTkLabel warnings in output
