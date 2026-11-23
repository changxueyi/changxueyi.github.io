# Blender scene (scripts/blender/)

`build_scene.py` runs in headless Blender (`-b --factory-startup`), execs the modules below into one
namespace, builds everything from `project.json`, saves `DIR/blender/scene.blend` (scene `TBV`, texture
paths made relative) and writes `DIR/blender/verify.json`. Rebuilding is cheap (~2 s) and overwrites
manual edits in scene.blend, so make lasting changes in project.json, not in the viewport.

| module | content |
|---|---|
| `tbv_cfg.py` | loads project.json; geometry constants; intro timing; `page_xy(px, py, role)`; `page_z`; highlight schedule `SCHED`; camera target `reading_target(t)` |
| `tbv_materials.py` | paper (texture × warm tint, roughness 0.78, noise bump), cloth board (colour sampled from the cover's spine edge), page-edge lines, marker (Transparent BSDF = multiply), card (alpha, DITHERED), fruit |
| `tbv_book.py` | boards, page blocks with gutter shape keys, pages (XZ grid 72×24, SimpleDeform BEND + Solidify 0.12 mm), intro baked per frame (LINEAR) |
| `tbv_camlight.py` | camera rig keys (BEZIER, AUTO_CLAMPED), world #121413, Key sun + Rim/Fill area lights, EEVEE settings |
| `tbv_overlays.py` | one band per OCR row segment, 2 mm above the paper, grows with scale X, fades with scale Y at the next sentence |
| `tbv_cards.py` | optional cards / props |
| `tbv_verify.py` | `footprint()`, `screen_bbox()`, `report()` |

## Fixed timeline (seconds)

0–1.0 closed book, slow push · 1.0–1.8 cover opens · 1.9–2.5 title page turns (blank flyleaf when there is
no title page) · 2.55–3.05 TOC entry highlighted, camera pushes in (no TOC page: a wide push instead) ·
3.30–4.31 TOC page + 3 fillers + last page riffle, the left page lands at 3.69–4.31 · 4.4 overview of the
reading page · 5.3 camera on the first line · reading from `intro_seconds` (5.4) · pull back to the open
book during the last ~1.3 s.

## Reading camera

Aim = (text-block centre x of the page being read, row centre y + 0.0128 m, page surface z), averaged
over a Hann window (2.0 s, shifted 0.45 s ahead) of the row being highlighted, sampled every 0.4 s.
Distance = text-block width / (0.654 × 0.94), clamped 0.20–0.32 m, ×1.035 at the start/end. Tilt ~9°,
lens 55 mm, f/11 focused on the aim. The read line sits at 60–66 % of the frame height, above the
captions (verify.json warns if a band leaves the frame or goes below 80 %).

## Cards (project.json `cards`, optional)

Floating paper-cut illustrations on a rig that follows the camera aim (70 %) 1.5 cm above it, so they
sit in the upper half of the frame with parallax. Each entry:

```json
{"image": "cards/platform.png", "w": 0.074, "h": 0.037, "layer": 1, "x": 0.0, "y": -0.0015,
 "from": 5, "to": null, "enter": "pop", "rot": 0, "tint": [1, 1, 1],
 "rot_keys": [[7, 6.0], [14, 0.0]], "flip": {"at": 14, "image": "cards/walk.png"}}
```

- `image`: RGBA PNG relative to the project (null = grey placeholder). `h` defaults to the image aspect.
- `w` metres (the frame is ~0.17 m wide while reading; 0.02–0.075 works). `layer` 1/2/3 = 6/13/24 mm
  above the page (more parallax and bigger on screen for higher layers); or give `z`.
- `x`, `y`: offset in the rig (x across the page, y up the page; ±0.03 stays in frame).
- `from` / `to`: sentence numbers (`i` in reading). Pops in 0.35 s before `from` starts; leaves 0.15 s
  after `to` ends (null = stays to the end). `enter`: `pop` (rises out of the page) or `top` (slides down).
- `rot_keys`: rotate about Z to the given degrees at the start of those sentences (e.g. a figure leaning).
- `flip`: a second image on the back; the card flips over at sentence `at`.

Make card PNGs with `scripts/prep_card.py` (grayscale paper-cut look, background removed).

## Props (project.json `props`, optional)

```json
{"kind": "fruit", "word": "橘子", "sentence": 3, "until": 4, "r": 0.0034, "color": [0.807, 0.184, 0.027]}
{"kind": "fruit", "attach": "rig", "x": -0.0148, "y": -0.0045, "z": 0.0195, "from": 15, "delay": 0.09, "r": 0.0026}
```

`word` props pop out of that word on the page when the highlight reaches it, bob, and float away after
sentence `until` (default ~4.5 s). `attach: rig` props sit among the cards (e.g. oranges in a figure's
arms). `kind`: `fruit` (with stem) or `ball`. Colours are linear RGB.

## The 背影 reference values

`/Users/changxueyi/Documents/ChatGPT/聊聊天/beiying_3d` holds the original hand-tuned project. Its cards in
this format: platform `{w .074, h .037, layer 1, y -.0015, from 5}`, father back/walk
`{w .020, h .030, layer 2, x -.012, y -.002, from 5, rot_keys [[7,6],[14,0]], flip {at 14}}`, train window
`{w .066, h .044, layer 3, x -.004, from 9, to 13, enter top}`, props: orange on 橘子 (sentence 3, until 4)
and three oranges `attach rig` from sentence 15.

## Blender 5.2 pitfalls

- A new world has no nodes: create Background + World Output yourself.
- Only `BLENDER_EEVEE` is in the engine enum. View transform Standard (Filmic/AgX wash out paper).
- Keyframe `hide_render` only (not `hide_viewport`); children do not inherit it, key them too.
- Set new-key interpolation via `preferences.edit.keyframe_new_interpolation_type`.
- `bpy_prop_collection` slices with a step fail: wrap in `list()`.
- Never call `read_factory_settings` in the live Blender: it unloads the MCP add-on. Build headless.
- Renders started with plain `nohup` inside an agent shell die with the session: `render.py` uses
  `start_new_session=True` and is resumable.
