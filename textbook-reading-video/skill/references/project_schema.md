# project.json (shared contract between the pipeline stages)

One project directory per video. All relative paths are relative to the project directory.
Stages only add/overwrite the keys they own; they must preserve every other key.

| key | owner | meaning |
|---|---|---|
| `version` | init | `1` |
| `slug` | init | ASCII id, used for file names |
| `root` | init | absolute project dir |
| `fps` | init | `30` |
| `title_text` | init / agent | small title shown 0–2.2 s at the top (default `那些长大后，才读懂的课文`) |
| `article_title` | init / agent | article name, used to find the TOC entry |
| `pages.cover/title_page/toc/left/right` | init | `{"src", "tex", "px": [w, h], "ocr"}`; `title_page`/`toc` may be `null`. `px` = pixel size of `src` (OCR coordinates are in this space). `left`/`right` = the two pages of the final open spread. |
| `fillers`, `endpaper` | init | riffle pages and endpaper textures |
| `book` | init | `{"W", "H"}` page size in metres (H = 0.26, W from the mean aspect of the left/right page images, clamped 0.165–0.205); optional `"cloth": [r, g, b]` (linear) overrides the board colour sampled from the cover edge |
| `text_block` | init | `{"left": [x0, x1], "right": [x0, x1]}` body-text column per page in px; the reading camera centres on it and fits its width |
| `toc_highlight` | init | `{"line_top","line_h","x0","x1"}` in toc px, or `null` |
| `reading` | align | list of `{"i", "text", "ratio", "segments": [{"page","line_top","line_h","x0","x1","weight"}], "chars": [{"c","page","line_top","line_h","x0","x1","exact"}]}` in reading order. `text` is exactly what is spoken and captioned (annotation marks removed). One segment per printed row the sentence touches, in that page's px; `line_top`/`line_h` = a constant-height line box per page centred on the OCR row; `weight` = spoken chars on that row (+0.5 per inner pause mark), used to grow the band across rows. `segments` is `[]` when the sentence is not on the page (no band). `page` may differ between segments when a sentence crosses from the left to the right page. `chars` = the spoken characters of `text` in order with their boxes (for props anchored on a word). `ratio` = share of exactly matched chars |
| `align` | align | `{"page": "right"/"left"/"both", "ratio", "split": "lines"/"para", "max_clause", "passage"}` – how `reading` was made |
| `voice`, `voice_style` | agent | MiMo preset voice (default `白桦`) and the style prompt (default male broadcast style) |
| `intro_seconds`, `outro_seconds`, `gap_comma`, `gap_full` | init | timing: first sentence starts at `intro_seconds` (5.4); pause after `，、：；` = `gap_comma` (0.30 s), after `。！？…` or closing quotes = `gap_full` (0.50 s); `outro_seconds` (1.3) after the last sentence |
| `timeline` | narrate | list of `{"i","text","start","end"}` (seconds, 3 decimals) – also written to `audio/timeline.json` |
| `duration` | narrate | total video seconds = last end + outro, rounded **up** to a whole frame |
| `audio` | narrate / mix | `{"lines_dir","narration","bgm","mix"}` |
| `highlight_color` | agent | marker transmittance RGB (linear); red `[0.91,0.33,0.30]`, yellow `[0.97,0.86,0.52]` |
| `cards`, `props` | agent | optional illustration cards / word props (see `references/blender_scene.md`) |
| `render` | init (defaults) | `{"frames_dir": "render/frames", "samples": 32, "percent": 100}`; read by `build_scene.py` and `render.py` (`--percent/--samples` override per run) |
| `out` | compose | output mp4 path |

Frame `0001.png` is t = 0.000 s; frame n is t = (n-1)/fps. Total frames = `round(duration*fps)`.
