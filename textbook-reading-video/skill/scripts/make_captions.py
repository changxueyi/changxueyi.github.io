#!/usr/bin/env python3
"""Write DIR/post/captions.ass (opening title + one caption per timeline sentence) from DIR/project.json.

usage: make_captions.py --project DIR

Timing (frame exact, hard cuts):
  sentence i is on screen from start_i - 0.08 s until sentence i+1 appears (start_{i+1} - 0.08 s), so
  adjacent captions never overlap and never leave a gap; the last one stays until
  min(end + 0.6, duration - 0.3). The title (project title_text) is shown 0-2.2 s.
  Every boundary is snapped to the first frame at/after it and written as a centisecond time strictly
  between two frames, so libass's millisecond truncation can never shift or double a frame.
Layout (measured on the 背影 video): Songti SC Regular 100 px, #1C1912, \\bord1, MarginV 88 (ink ~y 900-996)
  over a soft paper-white glow layer; title Songti SC 42 px #D9DAD3, top centre, MarginV 36, dark halo.
  Captions are always one line; a sentence wider than 1840 px at 100 px gets a smaller \\fs (reported).
Also writes DIR/post/captions_frames.json (frame ranges, font sizes, measured widths).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from post_common import (W, H, PostError, ass_time, between_frames_cs, captions_signature,  # noqa: E402
                         first_frame, get_duration, get_fps, get_timeline, get_title, load_project,
                         n_frames, run_main)

FONT, FONT_STYLE = "Songti SC", "Regular"   # Bold=0 -> weight 400 -> STSongti-SC-Regular
CAP_SIZE = 100            # libass maps Fontsize to winAscent+winDescent (= 1 em for Songti)
CAP_MAX_W = 1840          # 1920 - 2 x 40 px margins
CAP_MARGIN_V = 88         # bottom of the line box at y 992
CAP_COLOR = "&H0012191C"  # #1C1912
CAP_BORD = 1              # same-colour 1 px outline: slightly heavier strokes
GLOW_TAGS = "\\1a&HFF&\\3c&HF0F7FA&\\3a&H40&\\bord8\\blur6\\shad0"   # paper-white halo #FAF7F0, 25 % transparent
TITLE_SIZE = 42
TITLE_MARGIN_V = 36       # top of the line box at y 36
TITLE_COLOR = "&H00D3DAD9"  # #D9DAD3
TITLE_TAGS = "\\bord3\\blur4\\3c&H131412&\\3a&H30&\\shad0"           # dark soft halo
TITLE_START, TITLE_END = 0.0, 2.2
LEAD, LAST_HOLD, END_MARGIN = 0.08, 0.6, 0.3
MIN_SIZE = 60             # below this a sentence should be split upstream (still written, with a warning)


# ---- text measurement (same font file libass resolves) ------------------------------------------
def find_font(family=FONT, style=FONT_STYLE):
    """(path, index) of the face whose PIL name is (family, style), or (None, None)."""
    try:
        from PIL import ImageFont
    except ImportError:
        return None, None
    cands = []
    try:
        r = subprocess.run(["fc-match", "-f", "%{file}\t%{index}", f"{family}:style={style}"],
                           capture_output=True, text=True, timeout=20)
        f, _, i = r.stdout.partition("\t")
        if r.returncode == 0 and f:
            cands.append((f, int(i or 0)))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    for f in ("/System/Library/Fonts/Supplemental/Songti.ttc", "/Library/Fonts/Songti.ttc",
              os.path.expanduser("~/Library/Fonts/Songti.ttc")):
        if os.path.isfile(f):
            cands += [(f, i) for i in range(12)]
    for f, i in cands:
        try:
            if ImageFont.truetype(f, 100, index=i).getname() == (family, style):
                return f, i
        except (OSError, ValueError):
            continue
    return None, None


def em_per_size(path, index):
    """em / ASS font size: libass sets the size to winAscent + winDescent (hhea as fallback)."""
    try:
        from fontTools.ttLib import TTFont
        f = TTFont(path, fontNumber=index, lazy=True)
        upem = f["head"].unitsPerEm
        if "OS/2" in f and f["OS/2"].usWinAscent + f["OS/2"].usWinDescent > 0:
            return upem / (f["OS/2"].usWinAscent + f["OS/2"].usWinDescent)
        return upem / (f["hhea"].ascent - f["hhea"].descent)
    except Exception:  # fontTools missing or unreadable table: Songti's ratio is exactly 1
        return 1.0


class TextMeter:
    """Advance width of one line in PlayRes pixels at a given ASS font size."""

    def __init__(self):
        self.path, self.index = find_font()
        self.font, self.scale = None, 1.0
        if self.path:
            from PIL import ImageFont
            self.font = ImageFont.truetype(self.path, 1000, index=self.index)
            self.scale = em_per_size(self.path, self.index)

    def describe(self):
        if not self.font:
            return "estimate (Pillow or the Songti SC font file unavailable: 1 em per wide char, 0.55 em otherwise)"
        return f"{self.path}#{self.index} em/size {self.scale:.4f}"

    def width(self, text, size, bord=0):
        if self.font:
            w = self.font.getlength(text) * size * self.scale / 1000.0
        else:
            w = sum(1.0 if unicodedata.east_asian_width(c) in "WF" else 0.55 for c in text) * size
        return w + 2 * bord

    def fit(self, text, size, max_w, bord=0):
        """Largest integer size <= `size` whose line fits into max_w."""
        if self.width(text, size, bord) <= max_w:
            return size
        fs = int(size * max_w / self.width(text, size, bord))
        while fs > 1 and self.width(text, fs, bord) > max_w:
            fs -= 1
        return fs


def ass_text(text):
    """One line of literal text: no line breaks, no override blocks, no backslash escapes."""
    t = re.sub(r"\s*[\r\n]+\s*", "", text).strip()
    return t.replace("\\", "＼").replace("{", "｛").replace("}", "｝")


# ---- layout ---------------------------------------------------------------------------------------
def build(root, proj, meter=None):
    """Frame ranges, font sizes and widths of the title and every caption, plus the input signature."""
    fps, duration = get_fps(proj), get_duration(proj)
    timeline, title = get_timeline(root, proj), get_title(proj)
    meter = meter or TextMeter()
    nf = n_frames(duration, fps)
    notes, events = [], []
    for k, e in enumerate(timeline):
        s = max(0.0, e["start"] - LEAD)
        if k + 1 < len(timeline):
            end = max(0.0, timeline[k + 1]["start"] - LEAD)        # hard cut to the next caption
        else:
            end = min(e["end"] + LAST_HOLD, duration - END_MARGIN)
        f0, f1 = first_frame(s, fps), min(first_frame(end, fps), nf)
        if f1 <= f0:
            raise PostError(f"sentence {e['i']} gets no frames (shown {s:.3f}-{end:.3f} s, duration {duration})")
        text = ass_text(e["text"])
        if text != e["text"]:
            notes.append(f"sentence {e['i']}: line breaks / ASS special characters replaced -> {text}")
        fs = meter.fit(text, CAP_SIZE, CAP_MAX_W, CAP_BORD)
        if fs < CAP_SIZE:
            msg = (f"sentence {e['i']} is {meter.width(text, CAP_SIZE, CAP_BORD):.0f} px wide at {CAP_SIZE} px "
                   f"(> {CAP_MAX_W}): font size reduced to {fs} ({meter.width(text, fs, CAP_BORD):.0f} px)")
            if fs < MIN_SIZE:
                msg += f"; WARNING: below {MIN_SIZE} px, better split this sentence in the timeline"
            notes.append(msg)
        events.append(dict(i=e["i"], text=text, start=e["start"], end=e["end"], show=[round(s, 3), round(end, 3)],
                           f0=f0, f1=f1, cs0=between_frames_cs(f0, fps), cs1=between_frames_cs(f1, fps),
                           fs=fs, width=round(meter.width(text, fs, CAP_BORD), 1)))
    tdict = None
    if title:
        text = ass_text(title)
        fs = meter.fit(text, TITLE_SIZE, CAP_MAX_W)
        if fs < TITLE_SIZE:
            notes.append(f"title is {meter.width(text, TITLE_SIZE):.0f} px wide: font size reduced to {fs}")
        f0, f1 = first_frame(TITLE_START, fps), min(first_frame(TITLE_END, fps), nf)
        tdict = dict(text=text, f0=f0, f1=f1, cs0=between_frames_cs(f0, fps), cs1=between_frames_cs(f1, fps),
                     fs=fs, width=round(meter.width(text, fs), 1))
    return dict(fps=fps, duration=duration, n_frames=nf, title=tdict, events=events, notes=notes,
                measure=meter.describe(), signature=captions_signature(fps, duration, title, timeline),
                geometry=dict(caption_bottom=H - CAP_MARGIN_V, caption_size=CAP_SIZE, title_top=TITLE_MARGIN_V,
                              title_size=TITLE_SIZE, width=W, height=H))


def ass_lines(layout):
    fps = layout["fps"]
    styles = [
        f"Style: Caption,{FONT},{CAP_SIZE},{CAP_COLOR},{CAP_COLOR},{CAP_COLOR},&H00000000,"
        f"0,0,0,0,100,100,0,0,1,{CAP_BORD},0,2,40,40,{CAP_MARGIN_V},1",
        f"Style: Glow,{FONT},{CAP_SIZE},&HFF12191C,&HFF12191C,&H40F0F7FA,&HFF000000,"
        f"0,0,0,0,100,100,0,0,1,8,0,2,40,40,{CAP_MARGIN_V},1",
        f"Style: Title,{FONT},{TITLE_SIZE},{TITLE_COLOR},{TITLE_COLOR},{TITLE_COLOR},&H00000000,"
        f"0,0,0,0,100,100,0,0,1,0,0,8,40,40,{TITLE_MARGIN_V},1",
    ]
    lines = [
        "[Script Info]",
        "; Generated by textbook-reading-video/scripts/make_captions.py from project.json. Do not edit by hand.",
        "; Sentence i shows [start_i-0.08, start_{i+1}-0.08) (hard cut), the last until min(end+0.6, duration-0.3);",
        f"; boundaries are snapped to {fps} fps frames and written between two frames.",
        f"; tbv-signature: {layout['signature']}",
        "Title: textbook-reading-video captions",
        "ScriptType: v4.00+",
        f"PlayResX: {W}",
        f"PlayResY: {H}",
        "ScaledBorderAndShadow: yes",
        "WrapStyle: 2",
        "YCbCr Matrix: None",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        *styles,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    t = layout["title"]
    if t:
        fs = "" if t["fs"] == TITLE_SIZE else f"\\fs{t['fs']}"
        lines.append(f"Dialogue: 2,{ass_time(t['cs0'])},{ass_time(t['cs1'])},Title,,0,0,0,,"
                     f"{{{fs}{TITLE_TAGS}}}{t['text']}")
    for e in layout["events"]:
        a, b = ass_time(e["cs0"]), ass_time(e["cs1"])
        fs = "" if e["fs"] == CAP_SIZE else f"\\fs{e['fs']}"
        lines.append(f"Dialogue: 0,{a},{b},Glow,,0,0,0,,{{{fs}{GLOW_TAGS}}}{e['text']}")
        lines.append(f"Dialogue: 1,{a},{b},Caption,,0,0,0,,{{{fs}\\bord{CAP_BORD}\\shad0}}{e['text']}")
    return lines


def write_text(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, metavar="DIR", help="project directory containing project.json")
    a = ap.parse_args()
    root, proj = load_project(a.project)
    layout = build(root, proj)
    post = os.path.join(root, "post")
    os.makedirs(post, exist_ok=True)
    ass = os.path.join(post, "captions.ass")
    write_text(ass, "\n".join(ass_lines(layout)) + "\n")
    write_text(os.path.join(post, "captions_frames.json"), json.dumps(layout, ensure_ascii=False, indent=1) + "\n")
    fps = layout["fps"]
    t = layout["title"]
    if t:
        print(f"title  frames {t['f0']:4d}-{t['f1'] - 1:4d}  {ass_time(t['cs0'])}-{ass_time(t['cs1'])}"
              f"  {t['fs']:3d}px {t['width']:6.0f}px  {t['text']}")
    else:
        print("title  (none: title_text is empty)")
    for e in layout["events"]:
        print(f"{e['i']:5d}  frames {e['f0']:4d}-{e['f1'] - 1:4d}  {ass_time(e['cs0'])}-{ass_time(e['cs1'])}"
              f"  {e['fs']:3d}px {e['width']:6.0f}px  {e['text']}")
    for n in layout["notes"]:
        print("NOTE:", n)
    print(f"measure: {layout['measure']}")
    print(f"wrote {ass} ({len(layout['events'])} captions, {fps} fps, {layout['n_frames']} frames, "
          f"signature {layout['signature']})")
    return 0


if __name__ == "__main__":
    run_main(main)
