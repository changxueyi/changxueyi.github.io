#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QC of the audio stage: python3 verify_audio.py --project DIR [--lufs -14] [--tp -1.5]

Checks (ffprobe / ffmpeg ebur128 / numpy) and prints one line per check; exit code 1 if any fails:
  duration is frame aligned and = last end + outro rounded up to a frame; timeline starts at intro,
  gaps follow the punctuation rule, no overlaps; audio/timeline.json == project.timeline == reading;
  narration / bgm / mix are 48 kHz stereo with exactly round(duration * 48000) samples; one line clip
  per sentence (= speech + 2 x 30 ms); measured speech on/offset in narration_48k.wav vs timeline;
  silence between lines; mix loudness / true peak / DC / clipping; mix not shifted against narration;
  BGM fades to silence at both ends.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio_common as ac  # noqa: E402
import narrate  # noqa: E402

SR = ac.SR


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--lufs", type=float, default=-14.0)
    ap.add_argument("--tp", type=float, default=-1.5)
    args = ap.parse_args()
    d = ac.project_dir(args.project)
    proj = ac.load_project(d)
    fails = []

    def check(name, cond, detail=""):
        print(f"[{'ok' if cond else 'FAIL'}] {name}{': ' + detail if detail else ''}")
        if not cond:
            fails.append(name)

    fps = float(proj.get("fps") or 30)
    intro, outro = float(proj.get("intro_seconds", 5.4)), float(proj.get("outro_seconds", 1.3))
    gc, gf = float(proj.get("gap_comma", 0.30)), float(proj.get("gap_full", 0.50))
    tl = proj.get("timeline") or []
    duration = float(proj.get("duration") or 0)
    if not tl or duration <= 0:
        raise SystemExit("no timeline / duration in project.json: run narrate.py")
    ns = ac.samples_for(duration)
    nf = duration * fps
    check("duration", abs(nf - round(nf)) < 1e-4 and tl[-1]["end"] + outro - 1e-6 <= duration
          < tl[-1]["end"] + outro + 1 / fps, f"{duration:.6f} s = {round(nf)} frames, last end {tl[-1]['end']:.3f}"
          f" + outro {outro:g} = {tl[-1]['end'] + outro:.3f}")

    reading = [(int(r.get("i", k + 1)), str(r.get("text", "")).strip()) for k, r in enumerate(proj.get("reading") or [])]
    check("timeline matches reading", [(t["i"], t["text"]) for t in tl] == reading, f"{len(tl)} lines")
    tj = json.loads((d / "audio" / "timeline.json").read_text(encoding="utf-8"))
    check("audio/timeline.json == project.timeline", tj == tl)
    check("first start = intro_seconds", abs(tl[0]["start"] - intro) < 1e-6, f"{tl[0]['start']:.3f}")
    bad = []
    for k, t in enumerate(tl):
        if t["end"] <= t["start"]:
            bad.append(f"{t['i']}: end <= start")
        if k:
            want = narrate.gap_after(tl[k - 1]["text"], gc, gf)
            got = t["start"] - tl[k - 1]["end"]
            if got <= 0 or abs(got - want) > 0.0015:
                bad.append(f"{t['i']}: gap {got:.3f} != {want:.2f}")
    check("gaps / no overlap", not bad, "; ".join(bad) or ", ".join(
        f"{tl[k]['start'] - tl[k - 1]['end']:.3f}" for k in range(1, len(tl))))

    audio = proj.get("audio") or {}
    files = {k: d / audio.get(k, f"audio/{k}_48k.wav") for k in ("narration", "bgm", "mix")}
    data = {}
    for k, p in files.items():
        if not p.is_file():
            check(f"{k} file", False, f"missing {p}")
            continue
        pr = ac.probe(p)
        check(f"{k} format", pr["codec"] in ("pcm_s24le", "pcm_s16le") and pr["sr"] == SR and pr["ch"] == 2
              and pr["samples"] == ns, f"{pr['codec']} {pr['sr']} Hz {pr['ch']} ch {pr['samples']} samples "
              f"(want {ns}) = {pr['duration']:.6f} s")
        data[k] = ac.read_wav(p)[0]

    lines_dir = d / audio.get("lines_dir", "audio/lines")
    bad = []
    for t in tl:
        p = lines_dir / f"line_{t['i']:02d}.wav"
        if not p.is_file():
            bad.append(f"{p.name} missing")
            continue
        x, sr = ac.read_wav(p)
        want = t["end"] - t["start"] + 2 * narrate.MARGIN
        if sr != SR or x.shape[1] != 1 or abs(len(x) / SR - want) > 0.002:
            bad.append(f"{p.name}: {sr} Hz {x.shape[1]} ch {len(x) / SR:.3f}s (want {want:.3f}s)")
    check("line clips", not bad, "; ".join(bad) or f"{len(tl)} x 48 kHz mono, speech + 2 x 30 ms")

    if "narration" in data:
        nar = data["narration"][:, 0]
        rows, worst_s, worst_e = [], 0.0, 0.0
        for k, t in enumerate(tl):
            a = int((t["start"] - 0.25) * SR) if k == 0 else int((tl[k - 1]["end"] + t["start"]) / 2 * SR)
            b = int((t["end"] + 0.25) * SR) if k + 1 == len(tl) else int((t["end"] + tl[k + 1]["start"]) / 2 * SR)
            s0, s1, _ = ac.speech_bounds(nar[max(0, a):b])
            ms, me = (max(0, a) + s0) / SR, (max(0, a) + s1) / SR
            worst_s, worst_e = max(worst_s, abs(ms - t["start"])), max(worst_e, abs(me - t["end"]))
            rows.append(f"{t['i']}: {t['start']:.3f}/{ms:.3f} {t['end']:.3f}/{me:.3f}")
        check("timeline vs narration_48k.wav (timeline/measured)", worst_s <= 0.03 and worst_e <= 0.06,
              f"max |d start| {worst_s * 1000:.0f} ms, max |d end| {worst_e * 1000:.0f} ms | " + ", ".join(rows))
        loud = 10 * np.log10(np.mean(nar[int(tl[0]["start"] * SR):int(tl[-1]["end"] * SR)] ** 2) + 1e-20)
        gaps = []
        for k in range(1, len(tl)):
            g = nar[int((tl[k - 1]["end"] + narrate.MARGIN + 0.01) * SR):int((tl[k]["start"] - narrate.MARGIN - 0.01) * SR)]
            if len(g):
                gaps.append(10 * np.log10(np.mean(g ** 2) + 1e-20) - loud)
        check("silence between lines", all(v < -45 for v in gaps),
              "rel. level " + ", ".join(f"{v:.0f} dB" for v in gaps) if gaps else "single line")

    if "mix" in data:
        st = ac.ebur128(files["mix"])
        y = data["mix"]
        check("mix loudness", abs(st["I"] - args.lufs) <= 0.2, f"I {st['I']:.2f} LUFS (target {args.lufs:g}), "
              f"LRA {st['LRA']:.1f} LU")
        check("mix true peak", st["TP"] <= args.tp, f"{st['TP']:.2f} dBTP (max {args.tp:g})")
        clipped = int(np.sum(np.abs(y) >= 0.999))
        check("mix DC / clipping", np.abs(y.mean(axis=0)).max() < 1e-3 and clipped == 0,
              f"DC {np.abs(y.mean(axis=0)).max():.1e}, sample peak {ac.db(np.abs(y).max()):.2f} dBFS, "
              f"{clipped} clipped samples")
        if "narration" in data:
            w0 = int(tl[0]["start"] * SR)
            lag = ac.find_lag(data["narration"][:, 0], y[:, 0], w0, min(ns, w0 + 10 * SR), max_lag=300)
            check("mix aligned with narration", abs(lag) <= 2, f"lag {lag} samples")
    if "bgm" in data:
        bg = data["bgm"]
        edge = max(np.abs(bg[:48]).max(), np.abs(bg[-48:]).max())
        check("bgm fades / DC / peak", edge < 1e-3 and np.abs(bg.mean(axis=0)).max() < 1e-4
              and np.abs(bg).max() < 0.9, f"edge {edge:.1e}, DC {np.abs(bg.mean(axis=0)).max():.1e}, "
              f"peak {ac.db(np.abs(bg).max()):.2f} dBFS")
    print("ALL OK" if not fails else f"{len(fails)} check(s) failed: {', '.join(fails)}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
