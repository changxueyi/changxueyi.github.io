#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helpers for the audio stage (narrate.py, bgm.py, mix.py, verify_audio.py).

Needs only numpy and the ffmpeg / ffprobe binaries (no scipy, no soundfile).
  * WAV read (PCM 8/16/24/32, float32/64, WAVE_FORMAT_EXTENSIBLE) and atomic write (PCM16 + TPDF, PCM24)
  * ffmpeg helpers: decode any file to float, run a filter graph on a numpy array through pipes,
    EBU R128 measurement, loudnorm JSON parsing, lag search
  * project.json: load, and atomic update that only touches the caller's keys
  * speech span / pause detection shared by narrate.py and verify_audio.py
  * MiMo API key lookup (MIMO_API_KEY, then ~/.config/mimo/api_key). The key is never printed.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

SR = 48000
FRAME = 0.010
FF = ("ffmpeg", "-hide_banner", "-nostdin", "-nostats")
KEY_FILES = (Path("/Users/changxueyi/.config/mimo/api_key"), Path.home() / ".config" / "mimo" / "api_key")

_UMASK = os.umask(0)
os.umask(_UMASK)


# ------------------------------------------------------------------ secrets
def load_api_key() -> str:
    """MIMO_API_KEY env var first, then the private key file. Never log the return value."""
    key = os.environ.get("MIMO_API_KEY", "").strip()
    if key:
        return key
    for p in dict.fromkeys(KEY_FILES):
        if p.is_file():
            key = p.read_text(encoding="utf-8").strip()
            if key:
                return key
    raise RuntimeError("MiMo API key not found: set MIMO_API_KEY or create ~/.config/mimo/api_key")


# ------------------------------------------------------------------ files
def atomic_write_bytes(path, chunks) -> None:
    """Write to a temp file in the same directory, fsync, then rename over `path`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            for c in chunks:
                f.write(c)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o666 & ~_UMASK)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def atomic_write_text(path, text: str) -> None:
    atomic_write_bytes(path, [text.encode("utf-8")])


def read_wav(path):
    """Return (float64 array (n, ch) in [-1, 1), sample_rate)."""
    data = Path(path).read_bytes()
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError(f"not a RIFF/WAVE file: {path}")
    fmt = pcm = None
    pos = 12
    while pos + 8 <= len(data):
        cid = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        body = pos + 8
        if cid == b"fmt ":
            tag, ch, sr, _, block, bits = struct.unpack_from("<HHIIHH", data, body)
            if tag == 0xFFFE and size >= 40:  # WAVE_FORMAT_EXTENSIBLE: sub-format GUID starts with the tag
                tag = struct.unpack_from("<H", data, body + 24)[0]
            fmt = (tag, ch, sr, block, bits)
        elif cid == b"data":
            streamed = size in (0, 0xFFFFFFFF) or body + size > len(data)
            pcm = data[body:] if streamed else data[body:body + size]
            if fmt is not None:
                break
        pos = body + size + (size & 1)
    if fmt is None or pcm is None:
        raise ValueError(f"missing fmt or data chunk: {path}")
    tag, ch, sr, block, bits = fmt
    sw = block // ch
    n = len(pcm) // block
    pcm = pcm[: n * block]
    if tag == 1 and sw == 1:
        x = (np.frombuffer(pcm, np.uint8).astype(np.float64) - 128.0) / 128.0
    elif tag == 1 and sw == 2:
        x = np.frombuffer(pcm, "<i2") / 32768.0
    elif tag == 1 and sw == 3:
        b = np.frombuffer(pcm, np.uint8).reshape(-1, 3)
        u = np.zeros((b.shape[0], 4), np.uint8)
        u[:, 1:] = b
        x = (u.view("<i4").ravel() >> 8) / 8388608.0
    elif tag == 1 and sw == 4:
        x = np.frombuffer(pcm, "<i4") / 2147483648.0
    elif tag == 3 and sw in (4, 8):
        x = np.frombuffer(pcm, "<f4" if sw == 4 else "<f8").astype(np.float64)
    else:
        raise ValueError(f"unsupported wav format tag={tag} bytes/sample={sw}: {path}")
    return np.asarray(x, dtype=np.float64).reshape(-1, ch), sr


def write_wav(path, x, sr: int = SR, bits: int = 24, dither: bool = True, seed: int = 0) -> None:
    """Write float samples (n,) or (n, ch) in [-1, 1] as PCM16 (TPDF dither) or PCM24, atomically."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if not np.isfinite(x).all():
        raise ValueError(f"non-finite samples, refusing to write {path}")
    peak = float(np.abs(x).max()) if x.size else 0.0
    if peak > 1.0:
        print(f"WARNING: {Path(path).name}: peak {peak:.3f} > 1.0, samples will be clipped", file=sys.stderr)
    ch = x.shape[1]
    if bits == 16:
        y = x * 32767.0
        if dither:
            rng = np.random.default_rng(seed)
            y = y + (rng.random(y.shape) - rng.random(y.shape))
        data = np.clip(np.round(y), -32768, 32767).astype("<i2").tobytes()
    elif bits == 24:
        y = np.clip(np.round(x * 8388607.0), -8388608, 8388607).astype("<i4")
        data = np.ascontiguousarray(y).view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    else:
        raise ValueError("bits must be 16 or 24")
    block = ch * bits // 8
    pad = b"\0" if len(data) & 1 else b""
    hdr = (b"RIFF" + struct.pack("<I", 36 + len(data) + len(pad)) + b"WAVE"
           + b"fmt " + struct.pack("<IHHIIHH", 16, 1, ch, sr, sr * block, block, bits)
           + b"data" + struct.pack("<I", len(data)))
    atomic_write_bytes(path, [hdr, data, pad])


# ------------------------------------------------------------------ ffmpeg
def run(cmd, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    cmd = [str(c) for c in cmd]
    r = subprocess.run(cmd, input=input_bytes, capture_output=True)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", "replace")[-2500:]
        raise RuntimeError(f"command failed ({r.returncode}): {' '.join(cmd)[:400]}\n{err}")
    return r


_CAPS: dict = {}


def _cap(name: str) -> bool:
    if name not in _CAPS:
        if name == "soxr":
            r = subprocess.run([*FF, "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "0.05", "-af",
                                "aresample=48000:resampler=soxr", "-f", "null", "-"], capture_output=True)
            _CAPS[name] = r.returncode == 0
        elif name == "alimiter_latency":
            r = subprocess.run([*FF, "-h", "filter=alimiter"], capture_output=True, text=True)
            _CAPS[name] = "latency" in r.stdout
        else:
            raise KeyError(name)
    return _CAPS[name]


def resample_af(sr: int) -> str:
    return f"aresample={sr}:resampler=soxr:precision=28" if _cap("soxr") else f"aresample={sr}"


def limiter_af(limit_db: float, attack_ms: float = 1.5, release_ms: float = 60.0, sr: int = SR) -> str:
    """Look-ahead peak limiter run at 4x the sample rate (approximates a true-peak limiter)."""
    lat = ":latency=1" if _cap("alimiter_latency") else ""
    return (f"{resample_af(4 * sr)},alimiter=limit={10 ** (limit_db / 20):.6f}:attack={attack_ms}:"
            f"release={release_ms}:level=0{lat},{resample_af(sr)}")


def _as2d(x):
    x = np.asarray(x, dtype=np.float64)
    return (x[:, None], True) if x.ndim == 1 else (x, False)


def decode(path, sr: int = SR, ch: int = 1) -> np.ndarray:
    """Any audio file -> float64 (n, ch) at `sr` (high quality soxr resampling when available)."""
    r = run([*FF, "-i", path, "-af", resample_af(sr), "-ac", ch, "-ar", sr,
             "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1"])
    return np.frombuffer(r.stdout, "<f4").astype(np.float64).reshape(-1, ch)


def filt(x, af: str, sr: int = SR, out_sr: int | None = None):
    """Run an ffmpeg audio filter graph on a numpy array. Returns (y, ffmpeg_stderr_text)."""
    x2, mono = _as2d(x)
    ch = x2.shape[1]
    out_sr = out_sr or sr
    r = run([*FF, "-f", "f32le", "-ar", sr, "-ac", ch, "-i", "pipe:0", "-af", af, "-ar", out_sr, "-ac", ch,
             "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1"],
            np.ascontiguousarray(x2, dtype="<f4").tobytes())
    y = np.frombuffer(r.stdout, "<f4").astype(np.float64).reshape(-1, ch)
    return (y[:, 0] if mono else y), r.stderr.decode("utf-8", "replace")


def _num(pattern: str, text: str) -> float:
    m = re.search(pattern, text)
    if not m:
        raise RuntimeError(f"could not parse ffmpeg output ({pattern})")
    v = m.group(1)
    return float("-inf") if v == "-inf" else float(v)


def ebur128(src, sr: int = SR) -> dict:
    """EBU R128 (ffmpeg ebur128 filter) of an array (n,) / (n, ch) or a file:
    {'I': LUFS, 'LRA': LU, 'TP': dBTP}, read from the filter's frame metadata (0.001 resolution;
    the printed summary only has 0.1). A mono array is measured as one channel (dual mono = +3 LU)."""
    af = "ebur128=peak=true:metadata=1:framelog=quiet,ametadata=mode=print"
    if isinstance(src, (str, Path)):
        r = run([*FF, "-i", src, "-af", af, "-f", "null", "-"])
    else:
        x2, _ = _as2d(src)
        r = run([*FF, "-f", "f32le", "-ar", sr, "-ac", x2.shape[1], "-i", "pipe:0", "-af", af, "-f", "null", "-"],
                np.ascontiguousarray(x2, dtype="<f4").tobytes())
    err = r.stderr.decode("utf-8", "replace")

    def last(key):
        m = re.findall(rf"lavfi\.r128\.{key}=(-?inf|nan|-?[\d.]+)", err)
        return None if not m or m[-1] == "nan" else float(m[-1])

    i, lra, tp = last("I"), last("LRA"), last("true_peak")
    if i is not None and lra is not None and tp is not None:
        return {"I": i, "LRA": lra, "TP": 20 * np.log10(tp) if tp > 0 else float("-inf")}
    tail = err[err.rfind("Summary:"):]
    return {"I": _num(r"I:\s+(-?inf|-?[\d.]+) LUFS", tail),
            "LRA": _num(r"LRA:\s+(-?inf|-?[\d.]+) LU", tail),
            "TP": _num(r"Peak:\s+(-?inf|-?[\d.]+) dBFS", tail)}


def loudnorm_json(stderr_text: str) -> dict:
    i = stderr_text.rfind("{")
    j = stderr_text.rfind("}")
    if i < 0 or j < i:
        raise RuntimeError("loudnorm printed no JSON")
    return json.loads(stderr_text[i:j + 1])


def find_lag(ref, y, w0: int, w1: int, max_lag: int = 480) -> int:
    """Lag L (samples) maximising sum(ref[t] * y[t + L]) for t in [w0, w1); y delayed => L > 0."""
    w0 = max(w0, max_lag)
    w1 = min(w1, len(ref), len(y) - max_lag)
    if w1 <= w0:
        return 0
    a = ref[w0:w1]
    best, arg = -np.inf, 0
    for L in range(-max_lag, max_lag + 1):
        v = float(np.dot(a, y[w0 + L:w1 + L]))
        if v > best:
            best, arg = v, L
    return arg


def fit_length(x, n: int):
    """Trim or zero-pad axis 0 to exactly n samples."""
    if len(x) >= n:
        return x[:n]
    pad = np.zeros((n - len(x),) + x.shape[1:], dtype=x.dtype)
    return np.concatenate([x, pad])


def shift(x, lag: int):
    """Undo a delay of `lag` samples (lag > 0: x is late), keeping the length."""
    if lag == 0:
        return x
    z = np.zeros_like(x)
    if lag > 0:
        z[: len(x) - lag] = x[lag:]
    else:
        z[-lag:] = x[: len(x) + lag]
    return z


def probe(path) -> dict:
    r = run(["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_name,sample_rate,channels,bits_per_sample,duration_ts:format=duration",
             "-of", "json", path])
    d = json.loads(r.stdout)
    s = d["streams"][0]
    return {"codec": s.get("codec_name"), "sr": int(s.get("sample_rate", 0)), "ch": int(s.get("channels", 0)),
            "bits": int(s.get("bits_per_sample", 0)), "samples": int(s.get("duration_ts", -1)),
            "duration": float(d["format"]["duration"])}


def db(v: float) -> float:
    return 20.0 * np.log10(max(float(v), 1e-12))


# ------------------------------------------------------------------ project.json
def project_dir(d) -> Path:
    return Path(d).expanduser().resolve()


def load_project(d) -> dict:
    p = project_dir(d) / "project.json"
    if not p.is_file():
        raise SystemExit(f"project.json not found in {project_dir(d)}")
    return json.loads(p.read_text(encoding="utf-8"))


def update_project(d, top: dict | None = None, audio: dict | None = None) -> dict:
    """Re-read project.json, set only the given top-level keys / audio.* sub-keys, write atomically."""
    d = project_dir(d)
    proj = load_project(d)
    for k, v in (top or {}).items():
        proj[k] = v
    if audio:
        a = dict(proj["audio"]) if isinstance(proj.get("audio"), dict) else {}
        a.update(audio)
        proj["audio"] = a
    atomic_write_text(d / "project.json", json.dumps(proj, ensure_ascii=False, indent=1) + "\n")
    return proj


def frames_for(duration: float, fps: float) -> int:
    return int(round(duration * fps))


def samples_for(duration: float, sr: int = SR) -> int:
    return int(round(duration * sr))


# ------------------------------------------------------------------ speech detection
def frame_db(x, sr: int = SR, win: float = FRAME):
    n = max(1, int(round(sr * win)))
    m = len(x) // n
    fr = np.asarray(x[: m * n]).reshape(m, n)
    return 10.0 * np.log10((fr ** 2).mean(axis=1) + 1e-20), n


def runs(mask):
    """[(start, end)] index runs where mask is True."""
    d = np.diff(np.concatenate([[0], np.asarray(mask, dtype=np.int8), [0]]))
    return list(zip(np.nonzero(d == 1)[0].tolist(), np.nonzero(d == -1)[0].tolist()))


def speech_bounds(x, sr: int = SR, rel_db: float = -40.0, floor_db: float = -65.0, min_run: int = 5,
                  blip_rel_db: float = -20.0, blip_max: float = 0.35, blip_gap: float = 0.25):
    """(start_sample, end_sample, thr_db) of the speech in a mono signal.

    10 ms RMS frames above max(loudest_frame + rel_db, floor_db); runs shorter than `min_run` frames are
    ignored; a short quiet run (breath, click) separated from the rest by >= blip_gap s at either edge is
    dropped; both edges are refined to 1 ms."""
    x = np.asarray(x, dtype=np.float64)
    fdb, n = frame_db(x, sr)
    if len(fdb) == 0:
        return 0, len(x), floor_db
    top = float(fdb.max())
    thr = max(top + rel_db, floor_db)
    rr = [r for r in runs(fdb > thr) if r[1] - r[0] >= min_run]
    if not rr:
        return 0, len(x), thr

    def blip(r):
        return (r[1] - r[0]) * FRAME <= blip_max and float(fdb[r[0]:r[1]].max()) < top + blip_rel_db

    while len(rr) > 1 and blip(rr[0]) and (rr[1][0] - rr[0][1]) * FRAME >= blip_gap:
        rr.pop(0)
    while len(rr) > 1 and blip(rr[-1]) and (rr[-1][0] - rr[-2][1]) * FRAME >= blip_gap:
        rr.pop()
    a, b = rr[0][0] * n, rr[-1][1] * n
    k = max(1, int(sr * 0.001))

    def ms_db(i0, i1):
        seg = x[i0:i1]
        m = len(seg) // k
        if m == 0:
            return np.array([])
        return 10.0 * np.log10((seg[: m * k].reshape(m, k) ** 2).mean(axis=1) + 1e-20)

    i0 = max(0, a - n)
    hit = np.nonzero(ms_db(i0, a + n) > thr - 3.0)[0]
    start = i0 + int(hit[0]) * k if len(hit) else a
    hit = np.nonzero(ms_db(b - n, min(len(x), b + n)) > thr - 3.0)[0]
    end = (b - n) + (int(hit[-1]) + 1) * k if len(hit) else b
    return int(start), int(min(end, len(x))), float(thr)


def internal_pauses(x, start: int, end: int, thr_db: float, sr: int = SR, min_len: float = 0.15):
    """[(s0, s1)] absolute sample ranges inside [start, end) whose 10 ms frames stay below thr_db."""
    fdb, n = frame_db(np.asarray(x)[start:end], sr)
    return [(start + a * n, start + b * n) for a, b in runs(fdb < thr_db) if (b - a) * FRAME >= min_len]


def cap_pauses(seg, pauses, cap: float = 0.45, sr: int = SR, xfade: float = 0.015):
    """Shorten silent runs longer than their cap to the cap by cutting their middle with a short
    crossfade. `pauses` are (s0, s1) or (s0, s1, cap_s) relative to seg (cap_s overrides `cap`;
    cap <= 0 keeps the pause). Returns (new_seg, removed_samples)."""
    xf = int(xfade * sr)
    pieces, pos, removed = [], 0, 0
    for p in pauses:
        a, b = p[0], p[1]
        c = p[2] if len(p) > 2 else cap
        cap_n = max(int(c * sr), 2 * xf + 2)
        if c <= 0 or b - a <= cap_n:
            continue
        keep_l, keep_r = a + cap_n // 2, b - cap_n // 2
        pieces.append((pos, keep_l))
        pos = keep_r
        removed += keep_r - keep_l
    pieces.append((pos, len(seg)))
    if len(pieces) == 1:
        return np.array(seg, dtype=np.float64), 0
    out = np.array(seg[pieces[0][0]:pieces[0][1]], dtype=np.float64)
    fade_out = np.cos(np.linspace(0, np.pi / 2, xf)) ** 2
    fade_in = 1.0 - fade_out
    for p0, p1 in pieces[1:]:
        nxt = np.array(seg[max(0, p0 - xf):p1], dtype=np.float64)
        tail = out[-xf:] * fade_out + nxt[:xf] * fade_in
        out = np.concatenate([out[:-xf], tail, nxt[xf:]])
    return out, removed
