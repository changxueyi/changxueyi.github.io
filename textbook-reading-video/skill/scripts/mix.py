#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mix stage: duck the BGM under the narration, sum, master to -14 LUFS / <= -1.5 dBTP.

usage: python3 mix.py --project DIR [--duck -8] [--bgm-rel -7] [--lufs -14] [--tp -1.5]

reads   project.json: duration, timeline, audio.narration, audio.bgm. If the BGM length no longer
        matches duration (narrate.py was re-run), the BGM is re-rendered with its previous seed/key.
writes  audio/mix_48k.wav (48 kHz stereo 24-bit, exactly round(duration * 48000) samples)
updates project.json: audio.mix

Steps
  1. BGM gain: unducked BGM integrated loudness = narration loudness + --bgm-rel (LU).
  2. Duck --duck dB around every line: raised-cosine attack over the 0.30 s before the speech onset,
     hold, 0.80 s release starting 0.40 s after the line; gaps shorter than 1 s stay ducked.
  3. 10 Hz DC blocker, pre-gain, 4x-oversampled look-ahead limiter (ceiling = TP - 0.5 dB); the
     pre-gain is iterated (secant) until the ebur128 integrated loudness is within 0.05 LU of target.
     This keeps the loudnorm second pass linear (pure gain, no dynamic AGC). Nothing that shifts
     phase runs after the limiter (a high-pass there raised the true peak by ~0.5 dB).
  4. loudnorm pass 1 (measure true peak / LRA / threshold) + pass 2 (linear=true). measured_I is the
     ebur128 value: linear mode applies exactly target - measured_I, and ffmpeg's loudnorm and ebur128
     integrators differ by up to ~0.5 LU, so this makes the ebur128 reading land on the target.
  5. EBU R128 check of the result; retried with a lower ceiling if the true peak is over.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio_common as ac  # noqa: E402

SR = ac.SR
PRE, POST, FILL, ATTACK, RELEASE = 0.30, 0.40, 1.0, 0.30, 0.80


def duck_gain(timeline, ns: int, duck_db: float):
    """Per-sample linear gain for the BGM (1 = unducked) and the merged duck windows (s)."""
    iv = sorted((max(0.0, t["start"] - PRE), t["end"] + POST) for t in timeline)
    merged = []
    for a, b in iv:
        if merged and a - merged[-1][1] < FILL:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    g = np.zeros(ns)  # 0 = no duck, 1 = full duck
    for a, b in merged:
        i0, i1 = int(round(a * SR)), int(round((a + ATTACK) * SR))
        idx = np.arange(max(0, i0), min(ns, i1))
        g[idx] = np.maximum(g[idx], np.sin(np.pi / 2 * (idx - i0) / max(1, i1 - i0)) ** 2)
        g[max(0, i1):min(ns, int(round(b * SR)))] = 1.0
        r0, r1 = int(round(b * SR)), int(round((b + RELEASE) * SR))
        idx = np.arange(max(0, r0), min(ns, r1))
        g[idx] = np.maximum(g[idx], np.cos(np.pi / 2 * (idx - r0) / max(1, r1 - r0)) ** 2)
    return 10 ** (duck_db * g / 20), merged


def read_stereo(path: Path, what: str):
    if not path.is_file():
        raise SystemExit(f"{what} missing: {path}")
    x, sr = ac.read_wav(path)
    if sr != SR:
        raise SystemExit(f"{what}: {sr} Hz, expected {SR}")
    return np.repeat(x, 2, axis=1) if x.shape[1] == 1 else x[:, :2]


def loudnorm_measure(x, target_i: float, target_tp: float, lra: float) -> dict:
    af = f"loudnorm=I={target_i}:TP={target_tp}:LRA={lra}:print_format=json"
    r = ac.run([*ac.FF, "-f", "f32le", "-ar", SR, "-ac", x.shape[1], "-i", "pipe:0", "-af", af, "-f", "null", "-"],
               np.ascontiguousarray(x, dtype="<f4").tobytes())
    return ac.loudnorm_json(r.stderr.decode("utf-8", "replace"))


def master(pre, ns: int, target_i: float, target_tp: float, ceiling: float, win):
    """pre-gain + oversampled limiter (iterated onto target), then two-pass linear loudnorm."""
    g0 = target_i - ac.ebur128(pre)["I"]
    gain, hist = g0, []
    for _ in range(8):
        used = gain
        lim, _ = ac.filt(pre, f"highpass=f=10:poles=1,volume={gain:.4f}dB,"
                         + ac.limiter_af(ceiling, attack_ms=1.5, release_ms=80))
        lim = ac.fit_length(lim, ns)
        got = ac.ebur128(lim)["I"]
        hist.append((gain, got))
        if abs(got - target_i) <= 0.05:
            break
        slope = 1.0
        if len(hist) >= 2 and abs(hist[-1][0] - hist[-2][0]) > 1e-6:
            slope = min(1.0, max(0.2, (hist[-1][1] - hist[-2][1]) / (hist[-1][0] - hist[-2][0])))
        gain = min(gain + (target_i - got) / slope, g0 + 12.0)  # never more than 12 dB into the limiter
    limited_lu = (target_i - g0 + used) - got  # loudness the limiter took away
    lag = ac.find_lag(pre[:, 0], lim[:, 0], *win, max_lag=200)
    if abs(lag) >= 8:
        lim = ac.shift(lim, lag)
    lim_i = ac.ebur128(lim)["I"]
    m1 = loudnorm_measure(lim, target_i, target_tp, 20)
    lra = float(min(50.0, max(20.0, math.ceil(float(m1["input_lra"]) + 1))))
    if lra != 20:
        m1 = loudnorm_measure(lim, target_i, target_tp, lra)
    af = (f"loudnorm=I={target_i}:TP={target_tp}:LRA={lra}:linear=true:print_format=json:"
          f"measured_I={lim_i:.3f}:measured_TP={m1['input_tp']}:measured_LRA={m1['input_lra']}:"
          f"measured_thresh={m1['input_thresh']}:offset={m1['target_offset']},{ac.resample_af(SR)}")
    y, err = ac.filt(lim, af)
    m2 = ac.loudnorm_json(err)
    y = ac.fit_length(y, ns)
    lag2 = ac.find_lag(lim[:, 0], y[:, 0], *win, max_lag=200)
    if abs(lag2) >= 8:
        y = ac.shift(y, lag2)
    y = y - y.mean(axis=0)  # the limiter leaves a ~-68 dBFS offset on asymmetric speech peaks
    return y, {"gain": used, "iters": len(hist), "limited_lu": limited_lu, "lim_i": lim_i, "lag": lag,
               "lag2": lag2, "pass1": m1, "pass2": m2, "lra_target": lra}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, help="project directory containing project.json")
    ap.add_argument("--duck", type=float, default=-8.0, help="BGM attenuation under the narration, dB (-6..-9)")
    ap.add_argument("--bgm-rel", type=float, default=-7.0,
                    help="unducked BGM loudness relative to the narration, LU")
    ap.add_argument("--lufs", type=float, default=-14.0, help="integrated loudness target")
    ap.add_argument("--tp", type=float, default=-1.5, help="true-peak ceiling, dBTP")
    args = ap.parse_args()
    if not -9.0 <= args.duck <= -6.0:
        print(f"note: --duck {args.duck} dB is outside the usual -6..-9 dB range")

    d = ac.project_dir(args.project)
    proj = ac.load_project(d)
    timeline = proj.get("timeline") or []
    if not timeline or not proj.get("duration"):
        raise SystemExit("project.json has no timeline/duration: run narrate.py first")
    duration = float(proj["duration"])
    ns = ac.samples_for(duration)
    audio = proj.get("audio") or {}
    narr = read_stereo(d / audio.get("narration", "audio/narration_48k.wav"), "narration")
    if len(narr) != ns:
        raise SystemExit(f"narration has {len(narr)} samples, duration needs {ns}: re-run narrate.py")
    bgm_path = d / audio.get("bgm", "audio/bgm_48k.wav")
    bgm = read_stereo(bgm_path, "bgm") if bgm_path.is_file() else None
    if bgm is None or len(bgm) != ns:
        import bgm as bgm_mod
        print(f"BGM {'missing' if bgm is None else f'has {len(bgm)} samples'}, duration needs {ns}: re-rendering")
        bgm_mod.write_for_project(d)
        bgm_path = d / (ac.load_project(d).get("audio") or {}).get("bgm", "audio/bgm_48k.wav")
        bgm = read_stereo(bgm_path, "bgm")

    ln, lb = ac.ebur128(narr)["I"], ac.ebur128(bgm)["I"]
    gb = (ln + args.bgm_rel) - lb
    duck, merged = duck_gain(timeline, ns, args.duck)
    pre = narr + bgm * (10 ** (gb / 20)) * duck[:, None]
    st0 = ac.ebur128(pre)
    print(f"narration {ln:.2f} LUFS, bgm {lb:.2f} LUFS -> bgm gain {gb:+.2f} dB "
          f"({args.bgm_rel:+.1f} LU unducked), duck {args.duck:+.1f} dB")
    print("duck windows (s):", [(round(a, 2), round(b, 2)) for a, b in merged])
    print(f"premaster: I {st0['I']:.2f} LUFS, TP {st0['TP']:.2f} dBTP")

    ceiling = args.tp - 0.5
    w0 = int(timeline[0]["start"] * SR)
    win = (w0, min(ns, w0 + 10 * SR))  # alignment check window: first 10 s of narration
    for attempt in range(3):
        y, info = master(pre, ns, args.lufs, args.tp, ceiling, win)
        st = ac.ebur128(y)
        linear = info["pass2"].get("normalization_type") == "linear"
        if st["TP"] <= args.tp and linear:
            break
        print(f"retry: TP {st['TP']:.2f} dBTP, normalization {info['pass2'].get('normalization_type')}; "
              f"lowering limiter ceiling {ceiling:.2f} -> {ceiling - 0.5:.2f}")
        ceiling -= 0.5
    out = d / "audio" / "mix_48k.wav"
    ac.write_wav(out, y, bits=24)
    st = ac.ebur128(out)
    p1, p2 = info["pass1"], info["pass2"]
    print(f"limiter: pre-gain {info['gain']:+.2f} dB ({info['iters']} iterations, limiter took "
          f"{info['limited_lu']:.2f} LU), ceiling {ceiling:.2f} dBTP, lag {info['lag']}/{info['lag2']} samples")
    print(f"loudnorm pass 1: input_i {p1['input_i']} (ebur128 {info['lim_i']:.3f}) input_tp {p1['input_tp']} "
          f"input_lra {p1['input_lra']} thresh {p1['input_thresh']} offset {p1['target_offset']}")
    print(f"loudnorm pass 2: {p2.get('normalization_type')}, output_i {p2.get('output_i')} "
          f"output_tp {p2.get('output_tp')} (loudnorm's own meter)")
    print(f"mix_48k.wav (ebur128): I {st['I']:.2f} LUFS, LRA {st['LRA']:.1f} LU, TP {st['TP']:.2f} dBTP, "
          f"sample peak {ac.db(np.abs(y).max()):.2f} dBFS, DC {np.abs(y.mean(axis=0)).max():.1e}, "
          f"{len(y)} samples = {len(y) / SR:.6f} s")
    if st["TP"] > args.tp or abs(st["I"] - args.lufs) > 0.5:
        print("WARNING: master is outside the loudness / true-peak target")
    ac.update_project(d, audio={"mix": "audio/mix_48k.wav"})
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
