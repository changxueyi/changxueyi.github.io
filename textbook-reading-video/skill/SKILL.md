---
name: textbook-reading-video
description: Make a 3D textbook reading short video in the style of the 抖音 series 那些长大后，才读懂的课文 from photos or screenshots of a textbook. A Blender 3D book opens and riffles to the article, the camera reads a passage line by line with a marker highlight, Xiaomi MiMo TTS reads it in a male broadcast voice, Songti captions, 1920x1080 30 fps mp4 of about 20-45 s. Use when the user gives a cover image plus article page images (封面图, 文章页, optional 扉页/目录页 and the 片段文案 to read) with a MiMo API key, or asks for another 课文朗读视频 like the 背影 one.
---

# 课本朗读 3D 视频

Every video is one project directory with a `project.json`; each stage reads it and adds the keys it
owns (contract: `references/project_schema.md`). Scripts live in `S=<this skill dir>/scripts`.
Needs macOS (Vision OCR via swift, Songti font), python3 with numpy + Pillow, ffmpeg with libass,
Blender 5.2 at `/Applications/Blender.app` (override with env `BLENDER`).

## 0. Inputs

- Required: the cover image and the page image(s) that contain the passage.
- Optional: title page (扉页), TOC page (目录页; its entry for the article gets highlighted, needs
  `--article-title`), the facing page of the spread, the exact passage to read (片段文案),
  illustrations for floating cards.
- Spread roles: two article pages -> the even/earlier page is `--left`, the next is `--right`. One
  article page -> `--right` (a generated text page fills the left).
- The MiMo key is a TTS (语音合成) key even if the user calls it an ASR key. Ask only for missing
  required inputs; use defaults for the rest and state them.

## 1. API key

Never print, echo or log the key. Save it with python (not shell echo) to `~/.config/mimo/api_key`,
mode 600. If a different key is already there, copy the old file to `api_key.bak.<YYYYmmddHHMMSS>`
first. The scripts read env `MIMO_API_KEY` first, then that file, and mask the key in errors.

## 2. Create the project (~10-20 s)

```bash
python3 $S/init_project.py --root DIR --slug SLUG --cover COVER --right PAGE \
    [--left PAGE] [--title-page IMG] [--toc IMG --article-title 背影] [--title-text 那些长大后，才读懂的课文]
```

DIR must be new (e.g. `~/Documents/课本视频/SLUG`). Copies inputs, runs OCR, makes 3x text-page
textures, riffle fillers and the endpaper, and prints the OCR rows of the left/right pages.
Check `toc_highlight` is not null when a TOC was given.

## 3. Passage -> sentences and highlight boxes

```bash
python3 $S/align.py --project DIR --text "我说道：“爸爸，你走吧。”他往车外看了看说：……"
python3 $S/align.py --project DIR --text-file passage.txt   # several lines = one caption sentence per line
```

- No passage given: pick a contiguous, well-known, emotional passage of about 100-170 spoken
  characters from the OCR rows (25-40 s of speech), retype it with OCR errors fixed and without
  annotation marks (①®), run align, and tell the user which passage you chose.
- Gate: overall ratio >= 0.9 (< 0.8 means wrong page or differing text), no sentence with
  `segments: []` unless intended, sentences <= 18 characters (one caption line; otherwise pass lines).
- The passage may be on the left page, the right page or cross from left to right.

## 4. Narration, music, mix (~30 s)

```bash
python3 $S/narrate.py --project DIR        # one MiMo call per sentence, voice 白桦, writes timeline + duration
python3 $S/bgm.py --project DIR            # soft procedural piano bed
python3 $S/mix.py --project DIR            # ducking, -14 LUFS, true peak <= -1.5 dBTP
python3 $S/verify_audio.py --project DIR   # gate: ALL OK
```

- Redo single sentences with `narrate.py --only 3,7`, then rerun mix. Voice and style come from
  project.json `voice` (preset: 白桦 deep male, 苏打 brighter male) and `voice_style` (default: male
  broadcast style, calm and restrained, with the whole passage as unread context).
- Video length = 5.4 s intro + speech + 1.3 s outro. Changing `reading` later requires narrate again.

## 5. Optional illustration cards and props

Grayscale paper-cut cards float above the page in up to 3 depth layers (the reference look).
Add them only from user pictures or an image tool/skill that is actually available; otherwise skip
them (the video works without). Convert each picture, then add `cards` / `props` entries to
project.json (format and the 背影 example values in `references/blender_scene.md`):

```bash
python3 $S/prep_card.py picture.png DIR/cards/NAME.png [--mode cutout|card]
```

Time each card to the sentence it illustrates (`from`/`to`), use 1-3 cards, keep `w` 0.02-0.075 m.
A `word` prop (e.g. an orange popping out of 橘子) needs no image.

## 6. Build and check the 3D scene (~5 s, test stills ~10-30 s)

```bash
BLENDER=/Applications/Blender.app/Contents/MacOS/Blender
$BLENDER -b --factory-startup --python $S/blender/build_scene.py -- --project DIR
python3 $S/render.py --project DIR --test 1,61,95,133,170,MID1,MID2,LAST --percent 50 --samples 16
```

- Test stills go to `DIR/render/test/t_####.png`.
- Gate: the printed `TBV_BUILD {...}` line has `"warnings": []` (details in `DIR/blender/verify.json`:
  every band inside the frame and above the captions, no card over the line being read).
- Check test stills numerically when images are not visible to you: OCR them
  (`$(bash $S/ensure_ocr.sh) still.png` prints JSON lines with text boxes) and locate the marker
  (pixels with R-G > 45) to confirm it sits on the sentence being read.
- Live Blender via MCP (optional, when the user wants to see or tweak the scene): run
  `scripts/blender/mcp_open.py` with `execute_blender_code` after setting `BLEND = "DIR/blender/scene.blend"`
  in front of its code. It saves a copy of an unsaved session first, then opens the scene; wait ~2 s
  before the next MCP call, then `look` with `mode="camera"`. Never use `read_factory_settings`
  there (it unloads the MCP add-on). Bands are objects `TBV_HL_S<sentence>_<row>` that can be nudged
  along X/Y; save in Blender before rendering. Rebuilding overwrites such edits.

## 7. Render (detached, resumable)

```bash
python3 $S/render.py --project DIR [--fresh]          # 2 background Blender processes
python3 $S/render.py --project DIR --status           # or: --wait --timeout 1500
```

Full quality (100 %, 32 samples) runs at about 28 frames/min on an M3 with 16 GB: 40 s of video
(1200 frames) takes about 45 min, so tell the user the ETA and poll. `--percent 50 --samples 16`
gives a preview about 6x faster. Re-running continues where it stopped.

## 8. Captions, compose, final check (~2 min)

```bash
python3 $S/make_captions.py --project DIR
python3 $S/compose.py --project DIR        # -> DIR/out/SLUG.mp4 (frames smaller than 1080p are upscaled)
python3 $S/final_check.py --project DIR    # gate: exit 0 (format, caption OCR per sentence, title, loudness)
```

Deliver the absolute mp4 path, `DIR/out/preview_contact.jpg`, the passage, voice and duration.

## Defaults (project.json)

| key | default |
|---|---|
| `title_text` | 那些长大后，才读懂的课文 (shown 0-2.2 s) |
| `highlight_color` | red `[0.91, 0.33, 0.30]`; yellow marker `[0.97, 0.86, 0.52]` |
| `voice`, `voice_style` | 白桦, male broadcast style |
| `intro_seconds`, `outro_seconds` | 5.4 (fixed intro animation; do not change), 1.3 |
| `gap_comma`, `gap_full` | 0.30 s after ，、：；, 0.50 s after 。！？… or a closing quote |
| `render` | `{"frames_dir": "render/frames", "samples": 32, "percent": 100}` |

What to rerun after a change (after a new build_scene, render with `--fresh`: it moves the old
frames to `render/frames.bak.<time>`; render.py refuses to mix frames from an older scene):

| change | rerun |
|---|---|
| passage text | align, narrate, mix, build_scene, render, make_captions, compose, final_check |
| voice, style, gaps, `narrate --only` | narrate, mix, build_scene, render, make_captions, compose, final_check |
| cards, props, highlight colour | build_scene, render, compose, final_check |
| music / mix only | mix, compose, final_check |
| `title_text` | make_captions, compose, final_check |

## Troubleshooting

- Low match ratio: blurry or skewed photo; use a straight scan or screenshot at least 800 px wide,
  cropped to one page, or check that the passage is really on the given page.
- MiMo HTTP 401/403: wrong or expired key. HTTP 400: bad voice name. 5xx and truncated audio are retried.
- A caption sentence too long: captions shrink automatically; better split the passage into lines.
- `final_check` caption failures: rerun `make_captions.py` and `compose.py`; page text behind the
  captions is covered by the bottom paper fade.
- Blender details, camera rules and pitfalls: `references/blender_scene.md`.
- The original hand-tuned 背影 project for comparison: `/Users/changxueyi/Documents/ChatGPT/聊聊天/beiying_3d`.
