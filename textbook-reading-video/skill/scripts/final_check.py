#!/usr/bin/env python3
"""Final QA of the composed video. Prints a summary; exit 0 = no problems, 1 = problems, 2 = could not run.

usage: final_check.py --project DIR [--video PATH] [--allow-silent]

  format    ffprobe: duration, 1920x1080, fps, frame count = round(duration*fps), h264 yuv420p with BT.709
            tags, AAC 48 kHz stereo as long as the video, moov before mdat (faststart)
  captions  the frame at each sentence's midpoint ((start+end)/2): OCR of the caption box against the
            sentence text (differences in punctuation only are listed but pass)
  title     OCR at t = 1.0 s must read title_text; 0.4 s after the title ends it must be gone
  loudness  ebur128: integrated -14 LUFS +-3 LU (outside +-1 LU: warning), true peak <= -0.5 dBTP;
            a silent track is a problem unless --allow-silent
Writes DIR/out/preview_contact.jpg (12 evenly spaced frames, 4x3) and DIR/post/final_check.json.
OCR: the binary printed by scripts/ensure_ocr.sh (macOS Vision), falling back to $TBV_OCR.
"""
import argparse
import difflib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import unicodedata
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from post_common import (SCRIPTS_DIR, W, H, PostError, ffprobe_json, get_duration, get_fps,  # noqa: E402
                         load_project, n_frames, resolve, run_main)
import make_captions as mc  # noqa: E402

TARGET_I, I_TOL, I_WARN = -14.0, 3.0, 1.0      # LUFS (the mix stage targets -14 LUFS / -1.5 dBTP)
TP_MAX, TP_WARN = -0.5, -1.0                   # dBTP after AAC encoding
SILENT_I = -60.0
TITLE_AT, TITLE_GONE_AFTER = 1.0, 0.4          # s
TO_RGB = "scale=in_color_matrix=bt709:in_range=tv:flags=bicubic+accurate_rnd+full_chroma_int,format=rgb24"
QUOTES = {c: '"' for c in "“”„‟＂「」『』〝〞"}
QUOTES.update({c: "'" for c in "‘’‚‛＇"})


def tail(text, n=5):
    return " | ".join((text or "").strip().splitlines()[-n:])


def norm(s):
    """Fold full-width forms and quote styles, drop whitespace (OCR prints either form)."""
    s = unicodedata.normalize("NFKC", s)
    return "".join(QUOTES.get(c, c) for c in s if not c.isspace())


def bare(s):
    """Letters and digits only: no punctuation, symbols or spaces."""
    return "".join(c for c in unicodedata.normalize("NFKC", s) if unicodedata.category(c)[0] in "LMN")


def compare(got, want):
    if norm(got) == norm(want):
        return "OK"
    if bare(got) == bare(want):
        return "OK~"      # only punctuation differs (OCR often drops or swaps quote marks)
    return "BAD"


def find_ocr():
    """Path printed by scripts/ensure_ocr.sh; $TBV_OCR when that fails."""
    tried = []
    ens = os.path.join(SCRIPTS_DIR, "ensure_ocr.sh")
    if os.path.isfile(ens):
        cmd = [ens] if os.access(ens, os.X_OK) else ["/bin/zsh", ens]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
            if r.returncode == 0 and lines and os.access(lines[-1], os.X_OK):
                return lines[-1]
            tried.append(f"ensure_ocr.sh exit {r.returncode}: {tail(r.stderr or r.stdout, 3)}")
        except (OSError, subprocess.SubprocessError) as e:
            tried.append(f"ensure_ocr.sh: {e}")
    else:
        tried.append(f"{ens} not found")
    env = os.environ.get("TBV_OCR")
    if env and os.path.isfile(env) and os.access(env, os.X_OK):
        print(f"note     : OCR from $TBV_OCR={env} ({'; '.join(tried)})")
        return env
    tried.append("$TBV_OCR not set" if not env else f"$TBV_OCR={env} is not executable")
    raise PostError("no OCR tool: " + "; ".join(tried))


def run_ocr(tool, paths):
    """{abs path: [items in pixels, top-left origin] or None when the image could not be read}."""
    if not paths:
        return {}
    r = subprocess.run([tool, *paths], capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise PostError(f"OCR failed (exit {r.returncode}): {tail(r.stderr)}")
    res = {}
    lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
    for k, line in enumerate(lines):
        d = json.loads(line)
        key = os.path.abspath(d.get("file") or paths[k])
        if "error" in d or "items" not in d:
            res[key] = None
            continue
        wd, hd = d["W"], d["H"]
        res[key] = [dict(t=it.get("t", ""), c=round(float(it.get("c", 0)), 2),
                         x0=it["x"] * wd, x1=(it["x"] + it["w"]) * wd,
                         y0=(1 - it["y"] - it["h"]) * hd, y1=(1 - it["y"]) * hd) for it in d["items"]]
    return res


def extract_frames(video, frames, outdir):
    """Decode the video once and save the requested 0-based frames as RGB PNGs: {n: path}."""
    frames = sorted(set(frames))
    sel = "+".join(f"eq(n,{n})" for n in frames)
    pattern = os.path.join(outdir.replace("%", "%%"), "x_%04d.png")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-y", "-i", video, "-an",
                        "-vf", f"select='{sel}',{TO_RGB}", "-fps_mode", "passthrough", pattern],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise PostError(f"frame extraction failed: {tail(r.stderr)}")
    paths = {}
    for k, n in enumerate(frames):
        src = os.path.join(outdir, f"x_{k + 1:04d}.png")
        if os.path.isfile(src):
            paths[n] = os.path.join(outdir, f"frame_{n:05d}.png")
            os.replace(src, paths[n])
    return paths


def moov_first(path):
    """True if the moov atom precedes mdat (faststart), False if not, None if neither was found."""
    total = os.path.getsize(path)
    with open(path, "rb") as fh:
        pos = 0
        while pos + 8 <= total:
            fh.seek(pos)
            size, typ = struct.unpack(">I4s", fh.read(8))
            if size == 1:
                size = struct.unpack(">Q", fh.read(8))[0]
            elif size == 0:
                size = total - pos
            if typ == b"moov":
                return True
            if typ == b"mdat":
                return False
            if size < 8:
                return None
            pos += size
    return None


# ---- format / loudness -------------------------------------------------------------------------
def check_format(video, fps, duration, nf, problems):
    d = ffprobe_json(video, "-count_packets", "-show_streams", "-show_format")
    streams = d.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    info = dict(duration=float(d.get("format", {}).get("duration") or 0))
    if abs(info["duration"] - duration) > 0.5 / fps + 0.002:
        problems.append(f"format: duration {info['duration']:.3f}s, expected {duration:.3f}s")
    if not v:
        problems.append("format: no video stream")
    else:
        info.update(size=f"{v.get('width')}x{v.get('height')}", fps=v.get("r_frame_rate"),
                    frames=int(v.get("nb_frames") or -1), packets=int(v.get("nb_read_packets") or -1),
                    codec=f"{v.get('codec_name')} {v.get('profile')} {v.get('pix_fmt')}",
                    color="/".join(str(v.get(k)) for k in ("color_range", "color_space", "color_primaries",
                                                            "color_transfer")),
                    v_duration=float(v.get("duration") or 0))
        if (v.get("width"), v.get("height")) != (W, H):
            problems.append(f"format: video is {info['size']}, expected {W}x{H}")
        if Fraction(v.get("r_frame_rate", "0/1")) != Fraction(fps).limit_denominator(1001):
            problems.append(f"format: frame rate {info['fps']}, expected {fps}")
        if info["frames"] != nf or info["packets"] != nf:
            problems.append(f"format: {info['frames']} frames / {info['packets']} packets, expected {nf}")
        if v.get("codec_name") != "h264" or v.get("pix_fmt") != "yuv420p":
            problems.append(f"format: video codec {info['codec']}, expected h264 yuv420p")
        if info["color"] != "tv/bt709/bt709/bt709":
            problems.append(f"format: colour tags {info['color']}, expected tv/bt709/bt709/bt709")
    if not a:
        problems.append("format: no audio stream")
    else:
        info.update(a_codec=a.get("codec_name"), a_rate=int(a.get("sample_rate") or 0), a_channels=a.get("channels"),
                    a_duration=float(a.get("duration") or 0), a_kbps=round(int(a.get("bit_rate") or 0) / 1000))
        if info["a_rate"] != 48000:
            problems.append(f"format: audio {info['a_rate']} Hz, expected 48000")
        if info["a_codec"] != "aac" or info["a_channels"] != 2:
            problems.append(f"format: audio {info['a_codec']} {info['a_channels']} ch, expected aac stereo")
        if abs(info["a_duration"] - duration) > 0.03:
            problems.append(f"format: audio lasts {info['a_duration']:.3f}s, video {duration:.3f}s")
    info["faststart"] = moov_first(video)
    if info["faststart"] is not True:
        problems.append("format: moov atom is not in front of mdat (no +faststart)")
    return info


def loudness(video):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", video, "-map", "0:a:0", "-af",
                        "ebur128=peak=true:framelog=quiet", "-f", "null", "-"], capture_output=True, text=True)
    s = r.stderr[r.stderr.rfind("Summary:"):] if "Summary:" in r.stderr else ""

    def num(label, unit):
        m = re.search(label + r":\s+(-?(?:[\d.]+|inf)) " + unit, s)
        return float(m.group(1)) if m else None
    res = dict(I=num("I", "LUFS"), LRA=num("LRA", "LU"), TP=num("Peak", "dBFS"))
    if res["I"] is None:
        raise PostError(f"ebur128 measurement failed: {tail(r.stderr)}")
    return res


def judge_loudness(ld, allow_silent, problems, warnings):
    i, tp = ld["I"], ld["TP"]
    if i <= SILENT_I:
        (warnings if allow_silent else problems).append(f"loudness: audio is silent (I {i} LUFS)")
        return
    if abs(i - TARGET_I) > I_TOL:
        problems.append(f"loudness: integrated {i} LUFS, expected {TARGET_I} +- {I_TOL} LU")
    elif abs(i - TARGET_I) > I_WARN:
        warnings.append(f"loudness: integrated {i} LUFS (target {TARGET_I})")
    if tp is not None and tp > TP_MAX:
        problems.append(f"loudness: true peak {tp} dBTP > {TP_MAX}")
    elif tp is not None and tp > TP_WARN:
        warnings.append(f"loudness: true peak {tp} dBTP > {TP_WARN}")


# ---- OCR regions -------------------------------------------------------------------------------
MX, MY_CAP, MY_TITLE = 30, 40, 30     # crop margins around the expected line box (px)


def cap_top(e):
    return H - mc.CAP_MARGIN_V - e["fs"]


def caption_box(e):
    bottom = H - mc.CAP_MARGIN_V
    half = e["width"] / 2
    return (max(0, int(W / 2 - half - MX)), max(0, int(bottom - e["fs"] - MY_CAP)),
            min(W, int(W / 2 + half + MX)), min(H, int(bottom + MY_CAP)))


def title_box(t):
    top, half = mc.TITLE_MARGIN_V, t["width"] / 2
    return (max(0, int(W / 2 - half - MX)), max(0, top - MY_TITLE),
            min(W, int(W / 2 + half + MX)), min(H, top + t["fs"] + MY_TITLE))


def ink_only(img):
    """Dark caption ink as black on white; page text under the paper fade is lighter and disappears."""
    import numpy as np
    from PIL import Image
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    y = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    return Image.fromarray(np.where(y < 100, 0, 255).astype(np.uint8), "L")


def line_text(items, box, line_top, size):
    """Join the OCR items centred on the expected line box (crop coordinates), left to right."""
    cw, cy0 = box[2] - box[0], line_top - box[1] + size / 2
    keep = [it for it in (items or [])
            if MX - 20 <= (it["x0"] + it["x1"]) / 2 <= cw - MX + 20
            and abs((it["y0"] + it["y1"]) / 2 - cy0) <= 0.4 * size]
    return "".join(it["t"] for it in sorted(keep, key=lambda it: it["x0"]))


def contact_sheet(paths, frames, fps, out):
    from PIL import Image, ImageDraw, ImageFont
    tw, th, gap = 640, 360, 8
    sheet = Image.new("RGB", (4 * tw + 5 * gap, 3 * th + 4 * gap), (40, 40, 40))
    try:
        font = ImageFont.load_default(size=22)
    except TypeError:          # Pillow < 10.1
        font = ImageFont.load_default()
    for k, n in enumerate(frames):
        if n not in paths:
            continue
        im = Image.open(paths[n]).convert("RGB").resize((tw, th), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        label = f"{n / fps:6.2f}s  #{n + 1:04d}"
        x0, y0, x1, y1 = d.textbbox((12, 10), label, font=font)
        d.rectangle((x0 - 6, y0 - 4, x1 + 6, y1 + 4), fill=(0, 0, 0))
        d.text((12, 10), label, fill=(255, 255, 255), font=font)
        sheet.paste(im, (gap + (k % 4) * (tw + gap), gap + (k // 4) * (th + gap)))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out, quality=88)


# ---- main ----------------------------------------------------------------------------------------
RANK = {"OK": 2, "OK~": 1, "BAD": 0}


def check_captions(events, mids, paths, ocr_tool, work):
    from PIL import Image
    crops, rows = [], []
    for e, n in zip(events, mids):
        if n not in paths:
            continue
        crops.append(os.path.join(work, f"cap_{e['i']:03d}.png"))
        Image.open(paths[n]).crop(caption_box(e)).save(crops[-1])
    res = run_ocr(ocr_tool, crops)
    for e, n in zip(events, mids):
        if n not in paths:
            rows.append(dict(i=e["i"], frame=n, text=e["text"], ocr="(frame not in the video)", status="BAD",
                             via="-", ocr_crop="", fs=e["fs"], crop=None))
            continue
        p = os.path.join(work, f"cap_{e['i']:03d}.png")
        got = line_text(res.get(os.path.abspath(p)), caption_box(e), cap_top(e), e["fs"])
        rows.append(dict(i=e["i"], frame=n, text=e["text"], ocr=got, status=compare(got, e["text"]),
                         via="crop", ocr_crop=got, fs=e["fs"], crop=p))
    retry = [k for k, r in enumerate(rows) if r["status"] != "OK" and r["crop"]]
    if retry:   # page text showing through next to the caption: OCR the dark ink only
        inks = []
        for k in retry:
            inks.append(rows[k]["crop"][:-4] + "_ink.png")
            ink_only(Image.open(rows[k]["crop"])).save(inks[-1])
        res2 = run_ocr(ocr_tool, inks)
        for k, p in zip(retry, inks):
            e = events[k]
            got = line_text(res2.get(os.path.abspath(p)), caption_box(e), cap_top(e), e["fs"])
            st = compare(got, e["text"])
            if RANK[st] > RANK[rows[k]["status"]]:
                rows[k].update(ocr=got, status=st, via="ink-only crop")
    for r in rows:
        del r["crop"]
    return rows


def check_title(t, n_on, n_off, paths, ocr_tool, work):
    """OCR of the title box at n_on (must read the title) and n_off (must not); None = frame not in the video."""
    from PIL import Image
    box, crops = title_box(t), {}
    for tag, n in (("on", n_on), ("off", n_off)):
        if n in paths:
            crops[tag] = os.path.join(work, f"title_{tag}.png")
            Image.open(paths[n]).crop(box).save(crops[tag])
    res = run_ocr(ocr_tool, list(crops.values()))
    on = off = None
    if "on" in crops:
        on = line_text(res.get(os.path.abspath(crops["on"])), box, mc.TITLE_MARGIN_V, t["fs"])
    if "off" in crops:
        off = "".join(it["t"] for it in sorted(res.get(os.path.abspath(crops["off"])) or [], key=lambda it: it["x0"]))
    gone = None if off is None else (bare(t["text"]) not in bare(off) and
                                     difflib.SequenceMatcher(None, bare(t["text"]), bare(off)).ratio() < 0.6)
    return dict(text=t["text"], frame_on=n_on, ocr_on=on, status=compare(on, t["text"]) if on is not None else "BAD",
                frame_off=n_off, ocr_off=off, gone=gone)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, metavar="DIR", help="project directory containing project.json")
    ap.add_argument("--video", metavar="PATH", help="video to check (default: project.json out)")
    ap.add_argument("--allow-silent", action="store_true", help="silent audio is a warning, not a problem (tests)")
    a = ap.parse_args()
    root, proj = load_project(a.project)
    fps, duration = get_fps(proj), get_duration(proj)
    nf = n_frames(duration, fps)
    video = (os.path.abspath(os.path.expanduser(a.video)) if a.video else resolve(root, proj.get("out"))) or \
        os.path.join(root, "out", f"{proj.get('slug') or 'video'}.mp4")
    if not os.path.isfile(video):
        raise PostError(f"video not found: {video} (run compose.py first)")
    layout = mc.build(root, proj)
    ocr_tool = find_ocr()
    problems, warnings = [], []
    print(f"video    : {video}")
    fmt = check_format(video, fps, duration, nf, problems)
    print(f"format   : {fmt['duration']:.3f}s {fmt.get('size')} {fmt.get('fps')} fps {fmt.get('frames')} frames "
          f"({fmt.get('packets')} packets), {fmt.get('codec')} {fmt.get('color')}; {fmt.get('a_codec')} "
          f"{fmt.get('a_rate')} Hz {fmt.get('a_channels')} ch {fmt.get('a_kbps')} kb/s {fmt.get('a_duration', 0):.3f}s; "
          f"faststart {fmt['faststart']}")

    events, t = layout["events"], layout["title"]
    mids = [min(max(int(round((e["start"] + e["end"]) / 2 * fps)), e["f0"]), e["f1"] - 1) for e in events]
    sheet = [min(nf - 1, int(round((k + 0.5) * nf / 12))) for k in range(12)]
    n_on = min(max(int(round(TITLE_AT * fps)), t["f0"]), t["f1"] - 1) if t else None
    n_off = min(nf - 1, t["f1"] + int(round(TITLE_GONE_AFTER * fps))) if t else None
    wanted = [n for n in mids + sheet + [n_on, n_off] if n is not None and 0 <= n < nf]
    contact = os.path.join(root, "out", "preview_contact.jpg")
    with tempfile.TemporaryDirectory(prefix="tbv_check_") as work:
        paths = extract_frames(video, wanted, work)
        lost = sorted(set(wanted) - set(paths))
        if lost:
            problems.append(f"frames {lost[:8]} could not be decoded (video shorter than {nf} frames?)")
        rows = check_captions(events, mids, paths, ocr_tool, work)
        title = check_title(t, n_on, n_off, paths, ocr_tool, work) if t else None
        contact_sheet(paths, sheet, fps, contact)
    ok = sum(1 for r in rows if r["status"] != "BAD")
    print(f"captions : {ok}/{len(rows)} match ({sum(r['status'] == 'OK' for r in rows)} exact, "
          f"{sum(r['status'] == 'OK~' for r in rows)} punctuation-only differences)")
    for r in rows:
        r["t"] = round(r["frame"] / fps, 3)
        extra = "" if r["status"] == "OK" else f"   OCR: {r['ocr']!r}"
        if r["via"] == "ink-only crop":
            extra += f"  (ink-only crop; plain crop read {r['ocr_crop']!r})"
        print(f"  {r['i']:3d}  #{r['frame'] + 1:04d} {r['t']:7.2f}s  {r['status']:3s}  {r['fs']}px  {r['text']}{extra}")
        if r["status"] == "BAD":
            problems.append(f"caption {r['i']} at {r['t']:.2f}s: OCR {r['ocr']!r}, expected {r['text']!r}")
    if title:
        print(f"title    : {title['status']} at {n_on / fps:.2f}s OCR {title['ocr_on']!r}; at {n_off / fps:.2f}s "
              f"{ {True: 'gone', False: 'STILL VISIBLE', None: 'not checked'}[title['gone']]} (OCR {title['ocr_off']!r})")
        if title["status"] == "BAD":
            problems.append(f"title at {n_on / fps:.2f}s: OCR {title['ocr_on']!r}, expected {title['text']!r}")
        if title["gone"] is False:
            problems.append(f"title still visible at {n_off / fps:.2f}s: {title['ocr_off']!r}")
    else:
        print("title    : none (title_text is empty)")
    ld = loudness(video)
    judge_loudness(ld, a.allow_silent, problems, warnings)
    print(f"loudness : I {ld['I']} LUFS, LRA {ld['LRA']} LU, true peak {ld['TP']} dBTP (target {TARGET_I} LUFS)")
    print(f"contact  : {contact}")
    report = os.path.join(root, "post", "final_check.json")
    os.makedirs(os.path.dirname(report), exist_ok=True)
    with open(report, "w", encoding="utf-8") as fh:
        finite = {k: (v if v is None or abs(v) != float("inf") else None) for k, v in ld.items()}
        json.dump(dict(video=video, format=fmt, captions=rows, title=title, loudness=finite, contact=contact,
                       problems=problems, warnings=warnings), fh, ensure_ascii=False, indent=1)
    print(f"report   : {report}")
    for w_ in warnings:
        print(f"WARNING  : {w_}")
    for p in problems:
        print(f"PROBLEM  : {p}")
    print(f"RESULT   : {'FAIL' if problems else 'PASS'} ({len(problems)} problems, {len(warnings)} warnings)")
    return 1 if problems else 0


if __name__ == "__main__":
    run_main(main)
