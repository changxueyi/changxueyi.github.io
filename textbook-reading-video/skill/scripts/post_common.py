#!/usr/bin/env python3
"""Helpers shared by the post-stage scripts (make_captions, make_bottom_fade, compose, final_check).

Every script takes --project DIR and reads DIR/project.json (contract: references/project_schema.md).
Relative paths in project.json are relative to DIR. Frame 0001.png is t = 0; frame n is t = (n-1)/fps.
"""
import hashlib
import json
import math
import os
import shlex
import struct
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
W, H = 1920, 1080
DEFAULT_TITLE = "那些长大后，才读懂的课文"
LAYOUT_VERSION = 1   # bump when make_captions.py writes something different for the same inputs


class PostError(Exception):
    """Bad or missing input. Scripts print it without a traceback and exit with status 2."""


def run_main(main):
    try:
        sys.exit(main())
    except PostError as e:
        print(f"{os.path.basename(sys.argv[0])}: error: {e}", file=sys.stderr)
        sys.exit(2)
    except ModuleNotFoundError as e:
        print(f"{os.path.basename(sys.argv[0])}: error: Python module '{e.name}' is missing for {sys.executable} "
              "(the post scripts need numpy and Pillow; fontTools is optional)", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)


# ---- project.json -----------------------------------------------------------------------------
def load_project(project_dir):
    root = os.path.abspath(os.path.expanduser(project_dir))
    path = os.path.join(root, "project.json")
    if not os.path.isfile(path):
        raise PostError(f"project.json not found: {path}")
    with open(path, encoding="utf-8") as fh:
        try:
            proj = json.load(fh)
        except json.JSONDecodeError as e:
            raise PostError(f"{path}: invalid JSON: {e}") from None
    return root, proj


def resolve(root, p):
    """Absolute path for a project.json path value (relative values are relative to the project dir)."""
    if p is None or str(p).strip() == "":
        return None
    p = os.path.expanduser(str(p))
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(root, p))


def project_relpath(root, path):
    """Path relative to the project dir when it lies inside it, else absolute."""
    path = os.path.abspath(path)
    try:
        inside = os.path.commonpath([root, path]) == root
    except ValueError:
        inside = False
    return os.path.relpath(path, root) if inside else path


def update_project(root, updates):
    """Re-read project.json, overwrite only the given keys, write atomically; all other keys are kept.

    Same file format as tbv_common.save_project (indent=1, UTF-8 kept readable)."""
    path = os.path.join(root, "project.json")
    with open(path, encoding="utf-8") as fh:
        proj = json.load(fh)
    proj.update(updates)
    fd, tmp = tempfile.mkstemp(prefix=".project.json.", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(proj, fh, ensure_ascii=False, indent=1)
        os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def get_fps(proj):
    try:
        fps = float(proj.get("fps", 30))
    except (TypeError, ValueError):
        raise PostError(f"fps must be a number, got {proj.get('fps')!r}") from None
    if not 1 <= fps < 100:   # caption times are centiseconds placed between frames: needs fps < 100
        raise PostError(f"fps {fps} out of range (1..99)")
    return int(fps) if fps.is_integer() else fps


def get_duration(proj):
    if proj.get("duration") is None:
        raise PostError("project.json has no 'duration' (written by the narrate stage)")
    d = float(proj["duration"])
    if d <= 0:
        raise PostError(f"duration must be > 0, got {d}")
    return d


def n_frames(duration, fps):
    return int(round(duration * fps))


def get_title(proj):
    if "title_text" not in proj:
        return DEFAULT_TITLE
    t = proj["title_text"]
    return "" if t is None else str(t).strip()


def get_timeline(root, proj):
    """Sentences sorted by start: [{"i", "text", "start", "end"}]. Falls back to audio/timeline.json."""
    tl = proj.get("timeline")
    if tl is None:
        alt = os.path.join(root, "audio", "timeline.json")
        if os.path.isfile(alt):
            with open(alt, encoding="utf-8") as fh:
                tl = json.load(fh)
    if not tl:
        raise PostError("project.json has no 'timeline' (written by the narrate stage)")
    out = []
    for k, e in enumerate(tl):
        try:
            start, end = float(e["start"]), float(e["end"])
        except (KeyError, TypeError, ValueError):
            raise PostError(f"timeline[{k}] needs numeric start/end: {e!r}") from None
        text = str(e.get("text") or "").strip()
        if not text:
            raise PostError(f"timeline[{k}] has no text")
        if not 0 <= start < end:
            raise PostError(f"timeline[{k}] has start {start} / end {end}")
        out.append(dict(i=int(e.get("i", k + 1)), text=text, start=start, end=end))
    out.sort(key=lambda e: e["start"])
    return out


def captions_signature(fps, duration, title, timeline):
    """Fingerprint of everything captions.ass depends on (compose.py refuses a stale captions.ass)."""
    payload = dict(v=LAYOUT_VERSION, fps=fps, duration=round(duration, 4), title=title,
                   timeline=[[e["i"], e["text"], round(e["start"], 4), round(e["end"], 4)] for e in timeline])
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


# ---- frame time quantisation ----------------------------------------------------------------
def first_frame(t, fps):
    """0-based index of the first frame whose timestamp n/fps is >= t."""
    return max(0, math.ceil(round(t * fps, 6)))


def between_frames_cs(n, fps):
    """Centiseconds strictly between frame n-1 and frame n, i.e. frame n is the first one affected."""
    return 0 if n <= 0 else int(round((n - 0.5) * 100 / fps))


def ass_time(cs):
    h, rem = divmod(int(cs), 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


# ---- files / tools --------------------------------------------------------------------------
def png_info(path):
    """(width, height, colour_type) from the IHDR chunk; raises PostError for non-PNG files."""
    with open(path, "rb") as fh:
        head = fh.read(33)
    if len(head) < 33 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise PostError(f"not a PNG file: {path}")
    w, h = struct.unpack(">II", head[16:24])
    return w, h, head[25]


def ffprobe_json(path, *args):
    r = subprocess.run(["ffprobe", "-v", "error", *args, "-of", "json", path], capture_output=True, text=True)
    if r.returncode != 0:
        raise PostError(f"ffprobe failed on {path}: {r.stderr.strip()}")
    return json.loads(r.stdout)


def shell_join(cmd):
    return " ".join(shlex.quote(str(c)) for c in cmd)
