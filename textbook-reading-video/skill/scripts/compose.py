#!/usr/bin/env python3
"""Final composite: rendered PNG frames + mixed audio + paper bottom fade + captions/title -> H.264 mp4.

usage: compose.py --project DIR [--no-fade] [--allow-short] [--out PATH] [--dry-run]

Inputs (DIR/project.json): fps, duration, timeline, audio.mix, render.frames_dir (default render/frames), slug.
  Frames 0001.png ... (0001.png is t = 0), all the same size: 1920x1080, or any other 16:9 size such as a
  25-50 % test render, which is scaled to 1920x1080 with lanczos before the captions are drawn.
  Frame count = round(duration * fps); missing frames are an error unless --allow-short (the video then
  ends at the first missing frame).
  DIR/post/captions.ass from make_captions.py; refused when the timeline/title/fps/duration changed since.
  DIR/post/bottom_fade.png, created with the make_bottom_fade.py defaults when missing. It is enabled from
  first sentence start - 0.15 s to last sentence end + 0.2 s, with 0.3 s fade-in/out inside that window.
Output: DIR/out/<slug>.mp4 (or --out), recorded in project.json "out".
  libx264 preset slow CRF 17 High yuv420p, BT.709 tagged; AAC 192k 48 kHz stereo; +faststart.
Paths may contain spaces, quotes, ':' or non-ASCII characters: nothing goes through a shell, and the ASS file
is copied to a temp dir and handed to the ass filter by a plain relative name.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from post_common import (W, H, PostError, ass_time, captions_signature, ffprobe_json,  # noqa: E402
                         get_duration, get_fps, get_timeline, get_title, load_project, n_frames, png_info,
                         project_relpath, resolve, run_main, shell_join, update_project)
import make_bottom_fade  # noqa: E402

CRF, PRESET = 17, "slow"
FADE_PRE, FADE_POST, FADE_D = 0.15, 0.2, 0.3
CAPTION_FACE = "STSongti-SC-Regular"
TO_709 = ("scale=out_color_matrix=bt709:out_range=tv:flags=bicubic+accurate_rnd,format=yuv420p,"
          "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709")


def warn(msg):
    print(f"warning: {msg}", file=sys.stderr)


def tail(text, n=25):
    return "\n".join(text.strip().splitlines()[-n:])


def check_frames(frames_dir, nf, allow_short):
    """(usable frames from 0001.png on, their size). Every frame must be a complete PNG of one 16:9 size."""
    if not frames_dir or not os.path.isdir(frames_dir):
        raise PostError(f"frame directory not found: {frames_dir}")
    names = set(os.listdir(frames_dir))
    missing = [n for n in range(1, nf + 1) if f"{n:04d}.png" not in names]
    avail = missing[0] - 1 if missing else nf
    if missing:
        msg = f"{len(missing)} of {nf} frames missing in {frames_dir} (first: {missing[0]:04d}.png)"
        if not allow_short:
            raise PostError(msg + "; rerun with --allow-short to encode the frames before the first gap")
        if avail == 0:
            raise PostError(msg + "; nothing to encode")
        warn(f"{msg}; encoding 0001-{avail:04d}.png only ({avail} frames)")
    bad, sizes, alpha = [], set(), False
    for n in range(1, avail + 1):
        p = os.path.join(frames_dir, f"{n:04d}.png")
        try:
            w, h, ctype = png_info(p)
            with open(p, "rb") as fh:
                fh.seek(-12, os.SEEK_END)
                complete = fh.read(12)[4:8] == b"IEND"
        except (PostError, OSError) as e:
            bad.append(f"{n:04d}.png ({e})")
            continue
        if not complete:
            bad.append(f"{n:04d}.png (truncated, no IEND)")
        sizes.add((w, h))
        alpha |= ctype in (4, 6)
    if bad:
        raise PostError(f"{len(bad)} unreadable or truncated frames: " + "; ".join(bad[:5]))
    if len(sizes) != 1:
        raise PostError(f"frames must all have the same size, found {sorted(sizes)}")
    size = sizes.pop()
    if size != (W, H) and abs(size[0] * H - size[1] * W) > 0.01 * size[1] * W:
        raise PostError(f"frames are {size[0]}x{size[1]}: not 16:9, cannot be scaled to {W}x{H}")
    if alpha:
        warn("frames have an alpha channel; it is dropped (RGB values are used as they are)")
    return avail, size


def probe_audio(path):
    d = ffprobe_json(path, "-select_streams", "a:0", "-show_entries",
                     "format=duration:stream=codec_name,sample_rate,channels")
    if not d.get("streams"):
        raise PostError(f"no audio stream in {path}")
    s = d["streams"][0]
    return float(d.get("format", {}).get("duration") or 0.0), int(s.get("sample_rate") or 0), int(s.get("channels") or 0)


def check_captions(ass, root, proj):
    if not os.path.isfile(ass):
        raise PostError(f"{ass} not found: run make_captions.py --project {root} first")
    with open(ass, encoding="utf-8-sig") as fh:
        head = fh.read(4096)
    m = re.search(r"^; tbv-signature: (\w+)", head, re.M)
    want = captions_signature(get_fps(proj), get_duration(proj), get_title(proj), get_timeline(root, proj))
    if not m:
        warn(f"{ass} has no tbv-signature line (hand-made?): not checked against the timeline")
    elif m.group(1) != want:
        raise PostError(f"{ass} is out of date (timeline, title, fps or duration changed): "
                        f"rerun make_captions.py --project {root}")


def preflight_fonts(ass, work):
    """Render each Dialogue once on a tiny canvas and read libass's font selection log.

    Returns (primary faces, {codepoint: fallback face}, {codepoints without any font})."""
    out, k = [], 0
    with open(ass, encoding="utf-8-sig") as fh:
        for ln in fh.read().splitlines():
            if ln.startswith("Dialogue:"):
                parts = ln[len("Dialogue:"):].split(",", 9)
                if len(parts) == 10:
                    parts[1], parts[2] = ass_time(k * 10), ass_time(k * 10 + 10)   # 0.1 s slot each
                    ln = "Dialogue:" + ",".join(parts)
                    k += 1
            out.append(ln)
    if k == 0:
        return set(), {}, set()
    with open(os.path.join(work, "preflight.ass"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-v", "verbose", "-f", "lavfi", "-i",
                        f"color=c=gray:s=480x270:r=10:d={(k + 1) / 10:.1f}", "-vf", "ass=preflight.ass",
                        "-f", "null", "-"], cwd=work, capture_output=True, text=True)
    if r.returncode != 0:
        raise PostError("libass preflight failed:\n" + tail(r.stderr))
    primary, fallback, missing, pending = set(), {}, set(), None
    for line in r.stderr.splitlines():
        m = re.search(r"Glyph 0x([0-9A-Fa-f]+) not found", line)
        if m:
            pending = int(m.group(1), 16)
            continue
        m = re.search(r"failed to find any fallback with glyph 0x([0-9A-Fa-f]+)", line)
        if m:
            missing.add(int(m.group(1), 16))
            pending = None
            continue
        m = re.search(r"fontselect: \((.*?)\) -> (.*)$", line)
        if m:
            if pending is not None:
                fallback[pending] = m.group(2).strip()
            else:
                primary.add((m.group(1), m.group(2).strip()))
            pending = None
    return primary, fallback, missing


def check_fonts(ass, work):
    primary, fallback, missing = preflight_fonts(ass, work)
    for req, face in sorted(primary):
        print(f"libass : ({req}) -> {face}")
    if not primary:
        raise PostError("libass rendered no glyphs in the preflight (font lookup failed?)")
    wrong = [f"({req}) -> {face}" for req, face in primary if CAPTION_FACE not in face]
    if wrong:
        raise PostError(f"libass did not resolve every style to {CAPTION_FACE}: " + "; ".join(wrong))
    if fallback:
        warn("glyphs taken from fallback fonts: " +
             ", ".join(f"{chr(c)} U+{c:04X} -> {face}" for c, face in sorted(fallback.items())))
    if missing:
        raise PostError("no installed font has these characters (they would render as blanks): " +
                        ", ".join(f"{chr(c)} U+{c:04X}" for c in sorted(missing)))


def build_cmd(frames_dir, audio, mask, fps, nf_out, t_out, fade, tmp_out, src_size=(W, H)):
    pattern = os.path.join(frames_dir.replace("%", "%%"), "%04d.png")
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-v", "warning", "-nostats", "-progress", "pipe:1",
           "-framerate", str(fps), "-start_number", "1", "-pattern_type", "sequence", "-i", pattern,
           "-i", audio]
    base = "[0:v]format=rgb24,"
    if tuple(src_size) != (W, H):   # test renders: scale up before the captions are drawn at full size
        base += f"scale={W}:{H}:flags=lanczos+accurate_rnd,"
    base += "setsar=1"
    if mask:
        t0, t1, d = fade
        cmd += ["-loop", "1", "-framerate", str(fps), "-t", f"{t_out:.6f}", "-i", mask]
        graph = (f"{base}[base];"
                 f"[2:v]format=rgba,fade=t=in:st={t0:.3f}:d={d:.3f}:alpha=1,"
                 f"fade=t=out:st={t1 - d:.3f}:d={d:.3f}:alpha=1[mask];"
                 "[base][mask]overlay=0:0:format=rgb:eof_action=pass[bg];"
                 f"[bg]ass=captions.ass,{TO_709}[v];")
    else:
        graph = f"{base},ass=captions.ass,{TO_709}[v];"
    graph += "[1:a]apad[a]"      # a short mix is padded with silence; -t cuts everything at the duration
    cmd += ["-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-frames:v", str(nf_out),
            "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF), "-profile:v", "high",
            "-level:v", "4.1" if fps <= 30 else "4.2", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-t", f"{t_out:.6f}", "-movflags", "+faststart", tmp_out]
    return cmd


def run_ffmpeg(cmd, work, nf_out):
    log = os.path.join(work, "ffmpeg.log")
    with open(log, "w", encoding="utf-8", errors="replace") as ef:
        p = subprocess.Popen(cmd, cwd=work, stdout=subprocess.PIPE, stderr=ef, text=True)
        step = 10
        try:
            for line in p.stdout:
                if line.startswith("frame="):
                    n = int(line.split("=", 1)[1].strip() or 0)
                    pct = 100 * n // max(nf_out, 1)
                    if pct >= step:
                        print(f"encode : {n}/{nf_out} frames ({pct}%)", flush=True)
                        step = (pct // 10 + 1) * 10
            rc = p.wait()
        except BaseException:
            p.kill()
            p.wait()
            raise
    with open(log, encoding="utf-8", errors="replace") as fh:
        msgs = fh.read().strip()
    if rc != 0:
        raise PostError(f"ffmpeg failed (exit {rc}):\n{tail(msgs)}")
    if msgs:
        print("ffmpeg :", tail(msgs, 10).replace("\n", "\n         "))


def report(out):
    d = ffprobe_json(out, "-show_entries", "format=duration,size:stream=codec_type,codec_name,profile,width,height,"
                     "r_frame_rate,nb_frames,pix_fmt,color_space,color_primaries,color_transfer,sample_rate,"
                     "channels,duration")
    for s in d.get("streams", []):
        if s.get("codec_type") == "video":
            print(f"probe  : video {s.get('codec_name')} {s.get('profile')} {s.get('width')}x{s.get('height')} "
                  f"{s.get('r_frame_rate')} {s.get('nb_frames')} frames {s.get('pix_fmt')} "
                  f"{s.get('color_space')}/{s.get('color_primaries')}/{s.get('color_transfer')} {s.get('duration')}s")
        elif s.get("codec_type") == "audio":
            print(f"probe  : audio {s.get('codec_name')} {s.get('sample_rate')} Hz {s.get('channels')} ch "
                  f"{s.get('duration')}s")
    f = d.get("format", {})
    print(f"probe  : duration {f.get('duration')}s, {int(f.get('size', 0)) / 1e6:.1f} MB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, metavar="DIR", help="project directory containing project.json")
    ap.add_argument("--no-fade", action="store_true", help="no paper bottom fade behind the captions")
    ap.add_argument("--allow-short", action="store_true", help="encode up to the first missing frame")
    ap.add_argument("--out", metavar="PATH", help="output .mp4 (default DIR/out/<slug>.mp4)")
    ap.add_argument("--dry-run", action="store_true", help="check inputs and print the ffmpeg command only")
    a = ap.parse_args()
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise PostError(f"{tool} not found in PATH")
    root, proj = load_project(a.project)
    fps, duration = get_fps(proj), get_duration(proj)
    nf, timeline = n_frames(duration, fps), get_timeline(root, proj)
    slug = str(proj.get("slug") or "").strip() or \
        re.sub(r"[^A-Za-z0-9_-]+", "_", os.path.basename(root)).strip("_") or "video"
    frames_dir = resolve(root, (proj.get("render") or {}).get("frames_dir") or "render/frames")
    audio = resolve(root, (proj.get("audio") or {}).get("mix"))
    out = os.path.abspath(os.path.expanduser(a.out)) if a.out else os.path.join(root, "out", f"{slug}.mp4")
    if not out.lower().endswith((".mp4", ".m4v", ".mov")):
        raise PostError(f"output must end in .mp4/.m4v/.mov: {out}")

    avail, src_size = check_frames(frames_dir, nf, a.allow_short)
    t_out = duration if avail == nf else avail / fps
    if not audio:
        raise PostError("project.json has no audio.mix")
    if not os.path.isfile(audio):
        raise PostError(f"audio not found: {audio}")
    adur, arate, ach = probe_audio(audio)
    if adur + 0.0005 < t_out:
        warn(f"audio is {adur:.3f}s, shorter than the {t_out:.3f}s video: padded with silence")
    ass = os.path.join(root, "post", "captions.ass")
    check_captions(ass, root, proj)
    mask, fade = None, None
    if not a.no_fade:
        mask = os.path.join(root, "post", "bottom_fade.png")
        if not os.path.isfile(mask):
            if a.dry_run:
                print("mask   : missing, would be created with the make_bottom_fade.py defaults")
            else:
                print("mask   : created", make_bottom_fade.make_fade(mask))
        if os.path.isfile(mask):
            w, h, ctype = png_info(mask)
            if (w, h) != (W, H) or ctype != 6:
                raise PostError(f"{mask} must be a {W}x{H} RGBA PNG (got {w}x{h}, colour type {ctype})")
        t0 = max(0.0, timeline[0]["start"] - FADE_PRE)
        t1 = min(t_out, timeline[-1]["end"] + FADE_POST)
        if t1 <= t0:
            raise PostError(f"bottom fade window {t0:.3f}-{t1:.3f}s is empty")
        fade = (t0, t1, min(FADE_D, (t1 - t0) / 2))

    print(f"frames : {frames_dir} ({avail}/{nf} frames, {fps} fps, {t_out:.3f}s, {src_size[0]}x{src_size[1]})")
    if tuple(src_size) != (W, H):
        print(f"scale  : frames are {src_size[0]}x{src_size[1]}: scaled to {W}x{H} with lanczos before the "
              "captions are drawn" + (" (reduced-size test render)" if src_size[0] < W else ""))
    print(f"audio  : {audio} ({adur:.3f}s, {arate} Hz, {ach} ch)")
    print(f"ass    : {ass}")
    print("fade   : " + (f"{mask}, on {fade[0]:.3f}-{fade[1]:.3f}s, {fade[2]:.2f}s ramps" if mask else "off"))
    print(f"output : {out}")
    tmp_out = os.path.splitext(out)[0] + ".partial" + os.path.splitext(out)[1]
    with tempfile.TemporaryDirectory(prefix="tbv_compose_") as work:
        shutil.copyfile(ass, os.path.join(work, "captions.ass"))
        check_fonts(os.path.join(work, "captions.ass"), work)
        cmd = build_cmd(frames_dir, audio, mask, fps, avail, t_out, fade, tmp_out, src_size)
        print(f"cmd    : (cd {shell_join([work])} && {shell_join(cmd)})")
        if a.dry_run:
            return 0
        os.makedirs(os.path.dirname(out), exist_ok=True)
        try:
            run_ffmpeg(cmd, work, avail)
            os.replace(tmp_out, out)
        finally:
            if os.path.exists(tmp_out):
                os.unlink(tmp_out)
    update_project(root, {"out": project_relpath(root, out)})
    report(out)
    print(f"done   : {out} (project.json out = {project_relpath(root, out)})")
    if avail < nf:
        warn(f"video is short: {avail}/{nf} frames")
    return 0


if __name__ == "__main__":
    run_main(main)
