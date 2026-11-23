#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Narration stage: one MiMo TTS call per reading[] sentence -> clips, timeline, narration track.

usage:
  python3 narrate.py --project DIR [--voice 白桦] [--only 3,7] [--retries 3] [--workers 4]
                     [--max-pause 0.45] [--max-pause-mid 0.25]

reads   project.json: reading[].i/.text, voice, voice_style, intro_seconds, outro_seconds,
        gap_comma, gap_full, fps
writes  audio/raw/line_XX.wav + line_XX.json   raw MiMo audio + cache key (text/voice/style). Reused when
                                               the key matches; --only re-synthesizes the given i values.
        audio/lines/line_XX.wav                processed clip: 30 ms + speech + 30 ms, 48 kHz mono 24-bit
        audio/narration_48k.wav                48 kHz stereo (dual mono) 24-bit, exactly `duration` long
        audio/timeline.json                    [{"i","text","start","end"}] = speech on/offset in seconds
updates project.json: timeline, duration, audio.lines_dir, audio.narration (all other keys preserved)

TTS: voice = --voice / project.voice / 白桦; style = project.voice_style or the default male broadcast
style, followed by the whole text as "context only, do not read". A take is abnormal when its speech
(after the edit below) is < 0.5 s, > 0.6 s per spoken character (at least 1.2 s allowed) or
< 0.12 s per character (dropped words); abnormal takes and API errors are retried (--retries extra
attempts), and if every take is abnormal the closest one is kept with a WARNING.
Layout: line 1 speech starts at intro_seconds; start[k+1] = end[k] + gap, gap = gap_comma after
，、：；(or no final punctuation), gap_full after 。！？… or a closing quote.
duration = last end + outro_seconds, rounded up to a whole frame.
Clip edit: leading/trailing silence trimmed to 30 ms; silent pauses inside a line are shortened to
--max-pause where the text has punctuation and to --max-pause-mid elsewhere (TTS sometimes stalls
mid-phrase); timeline start/end are the speech on/offset.
Processing: per-clip loudness match (-26 LUFS), 80 Hz high-pass, light RMS compression, 4x-oversampled
peak limiter (keeps the -14 LUFS / -1.5 dBTP master in linear loudnorm). No reverb.
"""
import argparse
import base64
import hashlib
import json
import math
import os
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio_common as ac  # noqa: E402

API_URL = "https://api.xiaomimimo.com/v1/chat/completions"
MODEL = "mimo-v2.5-tts"
DEFAULT_VOICE = "白桦"
DEFAULT_STYLE = ("标准普通话男声播音腔，音色浑厚醇厚、略带磁性，字正腔圆、吐字清晰；"
                 "正常播音语速，节奏连贯，停顿简短；情绪深沉克制")
CONTEXT_NOTE = "（以下整段原文仅作语境参考，帮助语调连贯，不要朗读：{}）"
CONTEXT_MAX = 1000      # max characters of context per request (a window around the line if longer)
MARGIN = 0.030          # original audio kept before / after the speech in each clip (s)
MIN_SPEECH = 0.5        # s, shorter take = abnormal
MAX_PER_CHAR = 0.6      # s per spoken character, slower take = abnormal (never below 1.2 s per line)
MIN_PER_CHAR = 0.12     # faster than ~8 chars/s = words were probably dropped
LINE_LUFS = -26.0       # every clip is matched to this loudness before processing
VOICE_CEIL_DB = -14.4   # 4x-oversampled peak ceiling of the narration stem (PLR ~11.6 dB)
FULL_STOPS = set("。！？…!?.")
CLOSE_QUOTES = set("”’」』\"'")
CLOSE_BRACKETS = set("）)】]》〉")
PAUSE_PUNCT = set("，、；：。！？…—,;:.!?")

_print_lock = threading.Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def count_chars(text: str) -> int:
    """Spoken characters: letters (incl. CJK) and digits; punctuation and spaces excluded."""
    return sum(1 for c in text if unicodedata.category(c)[0] in "LN")


def punct_positions(text: str):
    """Relative positions (0..1, in spoken characters) of the punctuation inside a line that implies a pause."""
    total = count_chars(text)
    out, seen, group = [], 0, ""
    for c in text:
        if unicodedata.category(c)[0] in "LN":
            if seen and any(g in PAUSE_PUNCT for g in group):
                out.append(seen / total)
            group = ""
            seen += 1
        else:
            group += c
    return out


def pause_caps(pauses, a: int, b: int, text: str, cap_punct: float, cap_mid: float):
    """Give each detected pause a cap: cap_punct if it lines up (in speech time) with punctuation in the
    text, cap_mid otherwise. Returns [(s0, s1, cap)] relative to a."""
    if not pauses:
        return []
    speech = (b - a) - sum(p1 - p0 for p0, p1 in pauses)
    ppos, acc = [], 0
    for p0, p1 in pauses:
        ppos.append((p0 - a - acc) / max(speech, 1))
        acc += p1 - p0
    qpos = punct_positions(text)
    pairs = sorted((abs(p - q), i, j) for i, p in enumerate(ppos) for j, q in enumerate(qpos))
    hit, used = set(), set()
    for dist, i, j in pairs:
        if dist <= 0.15 and i not in hit and j not in used:
            hit.add(i)
            used.add(j)
    return [(p0 - a, p1 - a, cap_punct if i in hit else cap_mid) for i, (p0, p1) in enumerate(pauses)]


def duration_window(nchar: int):
    lo = max(MIN_SPEECH, MIN_PER_CHAR * nchar)
    hi = max(MAX_PER_CHAR * max(nchar, 1), MIN_SPEECH + 0.7)
    return lo, hi


def gap_after(text: str, gap_comma: float, gap_full: float) -> float:
    t = text.rstrip()
    if t and t[-1] in CLOSE_QUOTES:
        return gap_full
    while t and t[-1] in CLOSE_BRACKETS:
        t = t[:-1].rstrip()
    return gap_full if t and t[-1] in FULL_STOPS else gap_comma


def style_for(base: str, texts, k: int) -> str:
    lo = hi = k
    total = len(texts[k])
    grown = True
    while grown:
        grown = False
        if lo > 0 and total + len(texts[lo - 1]) <= CONTEXT_MAX:
            lo -= 1
            total += len(texts[lo])
            grown = True
        if hi < len(texts) - 1 and total + len(texts[hi + 1]) <= CONTEXT_MAX:
            hi += 1
            total += len(texts[hi])
            grown = True
    return base + CONTEXT_NOTE.format("".join(texts[lo:hi + 1]))


# ------------------------------------------------------------------ MiMo TTS
class TTSError(RuntimeError):
    def __init__(self, msg: str, fatal: bool = False):
        super().__init__(msg)
        self.fatal = fatal


def tts_request(text: str, voice: str, style: str, key: str, timeout: float = 120.0) -> bytes:
    payload = {"model": MODEL,
               "messages": [{"role": "user", "content": style}, {"role": "assistant", "content": text}],
               "audio": {"format": "wav", "voice": voice}}
    req = urllib.request.Request(API_URL, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"api-key": key, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")[:400].replace(key, "***")
        raise TTSError(f"HTTP {e.code}: {msg}", fatal=e.code in (400, 401, 403, 404)) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise TTSError(f"network error: {e}".replace(key, "***")) from None
    try:
        wav = base64.b64decode(json.loads(body)["choices"][0]["message"]["audio"]["data"])
    except Exception:
        raise TTSError("unexpected response: " + body[:300].decode("utf-8", "replace").replace(key, "***")) from None
    if wav[:4] != b"RIFF":
        raise TTSError("response audio is not a WAV file")
    return wav


def analyze(raw_path, text: str, caps) -> dict:
    """Decode a raw take to 48 kHz mono, find the speech, cap long internal pauses."""
    x = ac.decode(raw_path, ac.SR, 1)[:, 0]
    a, b, thr = ac.speech_bounds(x)
    ps = pause_caps(ac.internal_pauses(x, a, b, thr), a, b, text, *caps)
    seg, removed = ac.cap_pauses(x[a:b], ps)
    return {"x": x, "a": a, "b": b, "seg": seg, "removed": removed / ac.SR, "speech": len(seg) / ac.SR,
            "raw": len(x) / ac.SR, "pauses": [(round(p0 / ac.SR, 2), round((p1 - p0) / ac.SR, 2), c) for p0, p1, c in ps]}


def raw_paths(raw_dir: Path, i: int):
    return raw_dir / f"line_{i:02d}.wav", raw_dir / f"line_{i:02d}.json"


def cache_state(wav: Path, meta: Path, want: dict):
    if not wav.is_file():
        return False, "no raw take"
    if not meta.is_file():
        return True, "raw take without meta, reused"
    try:
        m = json.loads(meta.read_text(encoding="utf-8"))
    except Exception:
        return False, "unreadable meta"
    for k in ("text", "voice", "style_sha1", "model"):
        if m.get(k) != want[k]:
            return False, f"{k} changed"
    return True, "cached" + (" (abnormal duration, consider --only)" if m.get("abnormal") else "")


def synthesize(line: dict, voice: str, style: str, base_style: str, key: str, retries: int,
               caps, raw_dir: Path) -> dict:
    i, text = line["i"], line["text"]
    nchar = count_chars(text)
    lo, hi = duration_window(nchar)
    best, last_err, tries = None, None, 0
    for attempt in range(1, retries + 2):
        tries = attempt
        t0 = time.time()
        try:
            wav = tts_request(text, voice, style, key)
        except TTSError as e:
            last_err = str(e)
            log(f"[tts] line {i:02d} try {attempt}: {e}")
            if e.fatal:
                break
            time.sleep(min(2.0 * attempt, 8.0))
            continue
        tmp = raw_dir / f".line_{i:02d}.try{attempt}.wav"
        tmp.write_bytes(wav)
        try:
            info = analyze(tmp, text, caps)
        except Exception as e:  # undecodable audio counts as a failed attempt
            last_err = f"undecodable audio: {str(e)[:200]}"
            log(f"[tts] line {i:02d} try {attempt}: {last_err}")
            tmp.unlink(missing_ok=True)
            continue
        sp = info["speech"]
        dev = max(0.0, lo - sp) / lo + max(0.0, sp - hi) / hi
        log(f"[tts] line {i:02d} try {attempt}: speech {sp:.2f}s, {nchar} chars, {sp / max(nchar, 1):.2f}s/char, "
            f"window {lo:.2f}-{hi:.2f}s -> {'ok' if dev == 0 else 'ABNORMAL'} ({time.time() - t0:.1f}s)")
        if best is None or dev < best[0]:
            if best is not None:
                best[1].unlink(missing_ok=True)
            best = (dev, tmp, attempt, sp)
        else:
            tmp.unlink(missing_ok=True)
        if dev == 0:
            break
    if best is None:
        raise RuntimeError(f"line {i:02d}: no usable audio after {tries} attempt(s): {last_err}")
    dev, tmp, attempt, sp = best
    wav_path, meta_path = raw_paths(raw_dir, i)
    os.replace(tmp, wav_path)
    meta = {"i": i, "text": text, "voice": voice, "model": MODEL, "style_sha1": sha1(base_style),
            "style": base_style, "attempts": tries, "chosen_attempt": attempt, "speech_s": round(sp, 3),
            "abnormal": dev > 0, "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    ac.atomic_write_text(meta_path, json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
    if dev > 0:
        log(f"WARNING: line {i:02d}: every take had an abnormal duration; kept the closest ({sp:.2f}s)")
    return meta


# ------------------------------------------------------------------ build
def make_clip(raw_wav: Path, text: str, caps) -> dict:
    info = analyze(raw_wav, text, caps)
    x, a, b, seg = info["x"], info["a"], info["b"], info["seg"]
    m = int(round(MARGIN * ac.SR))
    pre = x[max(0, a - m):a]
    post = x[b:b + m]
    clip = np.concatenate([np.zeros(m - len(pre)), pre, seg, post, np.zeros(m - len(post))])
    fi, fo = int(0.008 * ac.SR), int(0.015 * ac.SR)
    clip[:fi] *= np.sin(np.linspace(0, np.pi / 2, fi)) ** 2
    clip[-fo:] *= np.cos(np.linspace(0, np.pi / 2, fo)) ** 2
    loud = ac.ebur128(clip)["I"]
    if not loud > -69.0:  # too short for a gated measurement: fall back to active-frame RMS
        fdb, _ = ac.frame_db(clip)
        act = fdb[fdb > fdb.max() - 20]
        loud = 10 * np.log10(np.mean(10 ** (act / 10))) - 0.691
    gain = float(np.clip(LINE_LUFS - loud, -24.0, 24.0))
    clip *= 10 ** (gain / 20)
    return {"clip": clip, "nseg": len(seg), "gain": gain, "removed": info["removed"], "raw": info["raw"],
            "lead": a / ac.SR, "trail": (len(x) - b) / ac.SR, "pauses": info["pauses"]}


def write_timeline_json(path: Path, timeline) -> None:
    rows = [f'{{"i":{t["i"]},"text":{json.dumps(t["text"], ensure_ascii=False)},'
            f'"start":{t["start"]:.3f},"end":{t["end"]:.3f}}}' for t in timeline]
    ac.atomic_write_text(path, "[\n" + ",\n".join(rows) + "\n]\n")


def build(d: Path, proj: dict, lines, caps) -> None:
    SR = ac.SR
    fps = float(proj.get("fps") or 30)
    intro = float(proj.get("intro_seconds", 5.4))
    outro = float(proj.get("outro_seconds", 1.3))
    gap_c = max(0.0, float(proj.get("gap_comma", 0.30)))
    gap_f = max(0.0, float(proj.get("gap_full", 0.50)))
    raw_dir, lines_dir = d / "audio" / "raw", d / "audio" / "lines"
    m = int(round(MARGIN * SR))

    clips = [make_clip(raw_paths(raw_dir, ln["i"])[0], ln["text"], caps) for ln in lines]
    timeline = []
    for k, (ln, c) in enumerate(zip(lines, clips)):
        start = intro if k == 0 else timeline[-1]["end"] + gap_after(lines[k - 1]["text"], gap_c, gap_f)
        start = round(start, 3)
        timeline.append({"i": ln["i"], "text": ln["text"], "start": start, "end": round(start + c["nseg"] / SR, 3)})
    n_frames = math.ceil((timeline[-1]["end"] + outro) * fps - 1e-6)
    duration = n_frames / fps
    ns = ac.samples_for(duration)

    dry = np.zeros(ns)
    spans = []
    for c, tl in zip(clips, timeline):
        c0 = int(round(tl["start"] * SR)) - m
        clip = c["clip"]
        if c0 < 0:
            clip, c0 = clip[-c0:], 0
        c1 = c0 + len(clip)
        if c1 > ns:
            raise RuntimeError(f"line {tl['i']}: clip ends after the track ({c1} > {ns} samples)")
        dry[c0:c1] += clip  # only the faded 30 ms margins can touch when a gap is < 60 ms
        spans.append((c0, c1))
    dry_peak = float(np.abs(dry).max())
    if dry_peak >= 0.98:
        raise RuntimeError(f"dry narration peak {dry_peak:.3f} would clip")

    af = ("highpass=f=80:poles=2,"
          f"acompressor=threshold={LINE_LUFS + 4:.1f}dB:ratio=2.5:attack=20:release=150:knee=2.83:"
          "detection=rms:makeup=1," + ac.limiter_af(VOICE_CEIL_DB, attack_ms=1.5, release_ms=60))
    wet, _ = ac.filt(dry, af)
    wet = ac.fit_length(wet, ns)
    c0, c1 = max(spans, key=lambda s: s[1] - s[0])
    lag = ac.find_lag(dry, wet, c0, c1)
    if abs(lag) >= 16:  # a real delay (e.g. limiter look-ahead without latency compensation)
        wet = ac.shift(wet, lag)
    peak = float(np.abs(wet).max())
    if peak >= 0.999:
        raise RuntimeError(f"processed narration peak {peak:.3f} would clip")

    lines_dir.mkdir(parents=True, exist_ok=True)
    keep = set()
    for tl, (s0, s1) in zip(timeline, spans):
        name = f"line_{tl['i']:02d}.wav"
        keep.add(name)
        ac.write_wav(lines_dir / name, wet[s0:s1], bits=24)
    for f in lines_dir.glob("line_*.wav"):
        if re.fullmatch(r"line_\d+\.wav", f.name) and f.name not in keep:
            f.unlink()
    narr_path = d / "audio" / "narration_48k.wav"
    ac.write_wav(narr_path, np.stack([wet, wet], axis=1), bits=24)
    write_timeline_json(d / "audio" / "timeline.json", timeline)
    old = proj.get("duration")
    ac.update_project(d, top={"timeline": timeline, "duration": round(duration, 6)},
                      audio={"lines_dir": "audio/lines", "narration": "audio/narration_48k.wav"})

    print("\n  i   start     end    dur    gap   gain  cut   text   [pauses: at s, length s, cap s]")
    for k, (tl, c) in enumerate(zip(timeline, clips)):
        gap = "    -" if k == 0 else f"{tl['start'] - timeline[k - 1]['end']:5.2f}"
        print(f"{tl['i']:3d} {tl['start']:7.3f} {tl['end']:7.3f} {tl['end'] - tl['start']:6.3f} {gap} "
              f"{c['gain']:+5.1f}dB {c['removed']:4.2f}  {tl['text']}  {c['pauses'] or ''}")
    st = ac.ebur128(np.stack([wet, wet], axis=1))
    print(f"\nprocessing lag {lag} samples{' (compensated)' if abs(lag) >= 16 else ''}; "
          f"narration I={st['I']:.1f} LUFS TP={st['TP']:.1f} dBTP sample-peak={ac.db(peak):.1f} dBFS")
    print(f"duration {duration:.6f} s = {n_frames} frames @ {fps:g} fps = {ns} samples "
          f"(last end {timeline[-1]['end']:.3f} + outro {outro:g})")
    if old is not None and abs(float(old) - duration) > 1e-6:
        print(f"duration changed {float(old):.6f} -> {duration:.6f}: re-run bgm.py and mix.py")
    print(f"wrote {narr_path}, {d / 'audio' / 'timeline.json'}, {lines_dir}/line_XX.wav")


def load_lines(proj: dict):
    reading = proj.get("reading") or []
    if not reading:
        raise SystemExit("project.json has no reading[] entries")
    lines, seen = [], set()
    for k, r in enumerate(reading):
        i = int(r.get("i", k + 1))
        text = str(r.get("text", "")).strip()
        if not text or count_chars(text) == 0:
            raise SystemExit(f"reading[{k}] (i={i}) has no speakable text")
        if i in seen:
            raise SystemExit(f"duplicate reading i={i}")
        seen.add(i)
        lines.append({"i": i, "text": text})
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, help="project directory containing project.json")
    ap.add_argument("--voice", help="MiMo preset voice (default: project.voice or 白桦)")
    ap.add_argument("--only", help="comma separated reading i values to re-synthesize, e.g. 3,7")
    ap.add_argument("--retries", type=int, default=3, help="extra attempts per line on API error / abnormal duration")
    ap.add_argument("--workers", type=int, default=4, help="parallel TTS requests")
    ap.add_argument("--max-pause", type=float, default=0.45,
                    help="cap (s) for silent pauses at punctuation inside a line (0 = keep)")
    ap.add_argument("--max-pause-mid", type=float, default=0.25,
                    help="cap (s) for silent pauses where the text has no punctuation (0 = keep)")
    args = ap.parse_args()

    caps = (max(0.0, args.max_pause), max(0.0, args.max_pause_mid))
    d = ac.project_dir(args.project)
    proj = ac.load_project(d)
    lines = load_lines(proj)
    ids = {ln["i"] for ln in lines}
    only = set()
    if args.only:
        try:
            only = {int(s) for s in re.split(r"[,\s]+", args.only.strip()) if s}
        except ValueError:
            raise SystemExit(f"--only expects comma separated integers, got {args.only!r}")
        if only - ids:
            raise SystemExit(f"--only: unknown reading i {sorted(only - ids)} (known: {sorted(ids)})")
    voice = args.voice or proj.get("voice") or DEFAULT_VOICE
    base_style = str(proj.get("voice_style") or DEFAULT_STYLE).strip()
    want = {"voice": voice, "style_sha1": sha1(base_style), "model": MODEL}
    raw_dir = d / "audio" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for f in raw_dir.glob(".line_*.try*.wav"):  # leftovers of an interrupted run
        f.unlink()

    todo = []
    for k, ln in enumerate(lines):
        wav, meta = raw_paths(raw_dir, ln["i"])
        if ln["i"] in only:
            todo.append(k)
            log(f"line {ln['i']:02d}: re-synthesize (--only)")
            continue
        ok, why = cache_state(wav, meta, {**want, "text": ln["text"]})
        log(f"line {ln['i']:02d}: {why}" + ("" if ok else " -> synthesize"))
        if not ok:
            todo.append(k)

    if todo:
        key = ac.load_api_key()
        texts = [ln["text"] for ln in lines]
        log(f"MiMo {MODEL}, voice {voice}, {len(todo)} request(s), style: {base_style} (+context)")
        failures = []
        with ThreadPoolExecutor(max_workers=max(1, min(args.workers, len(todo)))) as ex:
            futs = {ex.submit(synthesize, lines[k], voice, style_for(base_style, texts, k), base_style, key,
                              max(0, args.retries), caps, raw_dir): lines[k]["i"] for k in todo}
            for f in as_completed(futs):
                try:
                    f.result()
                except Exception as e:
                    msg = str(e)
                    failures.append(msg if msg.startswith("line ") else f"line {futs[f]:02d}: {msg}")
        if failures:
            raise SystemExit("TTS failed (successful lines are cached):\n  " + "\n  ".join(failures))
    build(d, proj, lines, caps)


if __name__ == "__main__":
    main()
