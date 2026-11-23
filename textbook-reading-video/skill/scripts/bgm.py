#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Procedural gentle, nostalgic piano BGM that fills project.duration exactly.

usage: python3 bgm.py --project DIR [--seed N] [--key Am]

  --seed  composition / humanisation seed; same seed + duration = same music
          (default: the previous run's seed from audio/bgm_48k.json, else crc32 of project.slug)
  --key   Am, Em, Dm, F#m, C, G, Bb ... (default: the previous run's key, else Am). Minor keys use
          i-VI-III-VII (= Am-F-C-G) phrases, major keys I-V-vi-IV.

Music: 4/4 at 66-70 BPM, the tempo chosen so a whole number of bars plus one ringing final chord fits
`duration`. 4-bar phrases (minor: i-VI-III-VII, i-v-VI-VII, iv-i-VI-VII, VI-III-VII-i, i-VI-iv-VII),
cadence bar Vsus4->V (VIIsus4->VII in minor), final rolled tonic add9 chord. Left hand broken chords,
sparse right-hand melody, very light string pad.
Sound: additive piano (inharmonic partials, 1-3 slightly detuned strings per note, two-stage
exponential decay, hammer noise, damper), detuned saw-ish string pad with vibrato, synthetic stereo
reverb IR (convolution), 30 Hz high-pass and -6 dB low shelf at 150 Hz (keeps the voice band clear),
1.5 s fade-in / 1.5 s fade-out, DC removed, peak -3 dBFS.

writes  audio/bgm_48k.wav (48 kHz stereo 24-bit, round(duration * 48000) samples)
        audio/bgm_48k.json (seed, key, bpm, chords ... ; mix.py uses it to re-render after a duration change)
updates project.json: audio.bgm
"""
import argparse
import json
import math
import re
import sys
import time
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio_common as ac  # noqa: E402

SR = ac.SR
FADE = 1.5
PEAK_DBFS = -3.0
BPM_MIN, BPM_MAX = 66.0, 70.0
NOTE_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
PC_NAME = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MINOR_DEG = {"i": (0, "m"), "III": (3, "M"), "iv": (5, "m"), "v": (7, "m"), "VI": (8, "M"), "VII": (10, "M")}
MAJOR_DEG = {"I": (0, "M"), "ii": (2, "m"), "iii": (4, "m"), "IV": (5, "M"), "V": (7, "M"), "vi": (9, "m")}
MINOR_PHRASES = [("i", "VI", "III", "VII"), ("i", "v", "VI", "VII"), ("iv", "i", "VI", "VII"),
                 ("VI", "III", "VII", "i"), ("i", "VI", "iv", "VII")]
MAJOR_PHRASES = [("I", "V", "vi", "IV"), ("vi", "IV", "I", "V"), ("I", "vi", "IV", "V"),
                 ("IV", "I", "V", "vi"), ("I", "iii", "IV", "V")]
MINOR_SCALE = (0, 2, 3, 5, 7, 8, 10)
MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
LH_VEL = (0.46, 0.33, 0.36, 0.38, 0.40, 0.36, 0.34, 0.32)
RHYTHMS = (((0, 2), (2, 1), (3, 1)), ((0, 3), (3, 1)), ((0, 2), (2, 2)), ((0, 1), (1, 1), (2, 2)),
           ((0, 1.5), (1.5, 0.5), (2, 2)), ((0, 2), (2, 1.5), (3.5, 0.5)))
END_RHYTHMS = (((0, 3), (3, 1)), ((0, 4),), ((0, 2), (2, 2)))
ARC = (-1.0, 2.0, 3.0, -1.5)  # melodic target offset (semitones) by position in the 4-bar phrase


def mtof(m):
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


def parse_key(s: str):
    m = re.fullmatch(r"\s*([A-Ga-g])([#b♯♭]?)(m|min|minor|M|maj|major)?\s*", s or "")
    if not m:
        raise SystemExit(f"bad --key {s!r} (examples: Am, Em, Dm, F#m, C, G, Bb)")
    pc = (NOTE_PC[m.group(1).upper()] + {"#": 1, "♯": 1, "b": -1, "♭": -1, "": 0}[m.group(2)]) % 12
    minor = m.group(3) in ("m", "min", "minor")
    return pc, minor, PC_NAME[pc] + ("m" if minor else "")


def fit_tempo(duration: float):
    """(bpm, progression bars, tail seconds for the final chord): prefer a 3.2-4.6 s tail."""
    best = None
    for bpm in np.arange(BPM_MIN, BPM_MAX + 1e-9, 0.05):
        bar = 240.0 / bpm
        for n in range(0, int(duration / bar) + 1):
            tail = duration - n * bar
            if tail < 1.6 and n > 0:
                continue
            cost = 3.0 * (3.2 - tail) if tail < 3.2 else 0.6 * max(0.0, tail - 4.6)
            cost += 0.02 * abs(bpm - 68.0) + (5.0 if n == 0 else 0.0)
            if best is None or cost < best[0] - 1e-12:
                best = (cost, round(float(bpm), 2), n, tail)
    return best[1], best[2], best[3]


def progression(n_bars: int, minor: bool, rng):
    phrases = MINOR_PHRASES if minor else MAJOR_PHRASES
    dom, pre = ("VII", "VI") if minor else ("V", "IV")
    seq = []
    while len(seq) < n_bars:
        if not seq:
            ph = phrases[0]
        else:
            ok = [p for p in phrases[1:] + phrases[:1] if p[0] != seq[-1]]
            ph = ok[int(rng.integers(len(ok)))]
        seq += list(ph)
    seq = seq[:n_bars]
    if n_bars >= 2:
        seq[-1] = dom
        if seq[-2] == dom:
            seq[-2] = pre
    return seq


def chord_tones(ch):
    third = {"M": 4, "m": 3, "sus4": 5}[ch["q"]]
    return {ch["root"] % 12, (ch["root"] + third) % 12, (ch["root"] + 7) % 12}, third


def chord_label(ch):
    s = PC_NAME[ch["root"]] + {"M": "", "m": "m", "sus4": "sus4"}[ch["q"]]
    return s + {None: "", "7": "7", "maj7": "maj7", "add9": "(add9)"}[ch.get("color")]


def pick_bass(ch, prev):
    """Bass in E2..D#3: root position, or first inversion when it gives a much smoother bass line."""
    root_b = 40 + (ch["root"] - 40) % 12
    if prev is None or ch["q"] == "sus4":
        return root_b
    _, third = chord_tones(ch)
    third_b = 40 + (ch["root"] + third - 40) % 12
    return third_b if abs(third_b - prev) + 3.5 < abs(root_b - prev) else root_b


def lh_notes(bass: int, ch):
    """Open broken chord: bass, then chord tones >= bass+6 at least 3 semitones apart; up and down."""
    tones, _ = chord_tones(ch)
    seq, nxt = [bass], bass + 6
    while len(seq) < 5:
        m = next(mm for mm in range(nxt, nxt + 13) if mm % 12 in tones)
        seq.append(m)
        nxt = m + 3
    if ch.get("color") in ("7", "maj7"):
        pc7 = (ch["root"] + (10 if ch["color"] == "7" else 11)) % 12
        seq[4] = next(mm for mm in range(seq[3] + 1, seq[3] + 13) if mm % 12 == pc7)
    return [seq[0], seq[1], seq[2], seq[3], seq[4], seq[3], seq[2], seq[1]]


def pad_voicing(ch, prev):
    """Close-position triad between F3 and A#4, voice-led from the previous one."""
    tones, _ = chord_tones(ch)
    cands = []
    for low in range(53, 62):
        if low % 12 not in tones:
            continue
        v, m = [low], low
        while len(v) < 3:
            m += 1
            if m % 12 in tones and all(m % 12 != x % 12 for x in v):
                v.append(m)
        if v[-1] <= 70:
            cands.append(v)
    if prev is None:
        return min(cands, key=lambda v: abs(sum(v) / 3.0 - 60.0))
    return min(cands, key=lambda v: sum(abs(a - b) for a, b in zip(v, prev)))


def melody_range(pc: int):
    s = (pc - 9 + 5) % 12 - 5  # transpose the A-minor tessitura (E4..G5) to the key
    return 64 + s, 79 + s


# ------------------------------------------------------------------ instruments
def piano_tone(midi: int, vel: float, n: int, rng):
    """Undamped additive piano tone of n samples. Partials with inharmonicity B, hammer-position comb,
    velocity-dependent brightness, 1-3 detuned strings (beating), two-stage exponential decay with
    faster decay for higher partials, 5 ms soft attack and a little low-passed hammer noise.
    The random draws do not depend on n, so a longer render has the same prefix."""
    f0 = mtof(midi)
    t = np.arange(n) / SR
    B = float(np.clip(1.4e-4 * (f0 / 100.0) ** 0.9, 6e-5, 1.2e-3))
    det_c = {1: (0.0,), 2: (-0.45, 0.45), 3: (-0.7, 0.05, 0.65)}[1 if f0 < 70 else (2 if f0 < 140 else 3)]
    tau_slow = 2.4 * (261.6 / f0) ** 0.55
    tau_fast = 0.42 * (261.6 / f0) ** 0.5
    k_bright = 0.34 - 0.20 * vel
    out = np.zeros(n)
    for k in range(1, int(min(26, 7500.0 / f0)) + 1):
        fk = k * f0 * math.sqrt(1.0 + B * k * k)
        if fk > 0.42 * SR:
            break
        amp = k ** -0.85 * math.exp(-(k - 1) * k_bright) * (0.15 + 0.85 * abs(math.sin(math.pi * k / 7.3)))
        if amp < 2e-4:
            continue
        ts = tau_slow / (1.0 + 0.22 * (k - 1))
        tf = tau_fast / (1.0 + 0.30 * (k - 1))
        draws = [(rng.normal(0, 0.12), rng.uniform(0, 2 * np.pi)) for _ in det_c]
        nk = min(n, int(ts * math.log(0.38 * amp / 1e-6) * SR) + 1)  # until the partial is < -120 dB
        tk = t[:nk]
        s = np.zeros(nk)
        for dc, (jit, ph) in zip(det_c, draws):
            s += np.cos(2 * np.pi * fk * 2.0 ** ((dc + jit) / 1200.0) * tk + ph)
        out[:nk] += amp * (0.62 * np.exp(-tk / tf) + 0.38 * np.exp(-tk / ts)) * s / len(det_c)
    na = int(0.005 * SR)
    out[:na] *= np.sin(np.linspace(0, np.pi / 2, na)) ** 2
    nn = int(0.03 * SR)
    noise = rng.standard_normal(nn)
    spec = np.fft.rfft(noise) / (1.0 + (np.fft.rfftfreq(nn, 1 / SR) / (900 + 1500 * vel)) ** 2)
    noise = np.fft.irfft(spec, nn) * np.exp(-np.arange(nn) / (0.008 * SR))
    out[:min(nn, n)] += (0.025 * vel * noise / (np.abs(noise).max() + 1e-9))[:min(nn, n)]
    return out


class Piano:
    """Renders notes from a bank of undamped tones: (midi, brightness layer, round-robin variant)."""

    def __init__(self, seed: int):
        self.seed = seed
        self.need, self.bank = {}, {}

    @staticmethod
    def layer(vel: float) -> int:
        return int(np.clip(round((vel - 0.30) / 0.08), 0, 3))

    def plan(self, midi: int, vel: float, hold: float, release: float, variant: int):
        key = (int(midi), self.layer(vel), int(variant))
        n = int((hold + 7.0 * release + 0.05) * SR)
        self.need[key] = max(self.need.get(key, 0), n)
        return key, n

    def build(self):
        for key, n in sorted(self.need.items()):
            rng = np.random.default_rng([self.seed, key[0], key[1], key[2]])
            self.bank[key] = piano_tone(key[0], 0.30 + 0.08 * key[1], n, rng)

    def render(self, key, n: int, vel: float, hold: float, release: float):
        out = self.bank[key][:n].copy()
        h = int(hold * SR)
        if h < n:  # damper
            out[h:] *= np.exp(-(np.arange(n - h) / SR) / release)
        fo = min(n, int(0.02 * SR))
        out[n - fo:] *= np.linspace(1, 0, fo)
        reg = float(np.clip((mtof(key[0]) / 261.6) ** 0.35, 0.5, 1.2))  # lighter low register
        return out * (vel ** 1.7) * 0.25 * reg


def pan_gains(p: float):
    return math.cos(p * math.pi / 2), math.sin(p * math.pi / 2)


def pitch_pan(m: int) -> float:
    return float(np.clip(0.5 + (m - 60) / 110.0, 0.36, 0.66)) if m >= 45 else 0.5


def pad_chord(midis, dur: float, rng, attack: float = 1.4, release: float = 1.6):
    """Soft string-ensemble pad: band-limited saw-like additive tone, 3 detuned voices per note with
    slow vibrato and drift, spread L/C/R. Returns a stereo array of dur + release seconds."""
    n = int((dur + release) * SR)
    t = np.arange(n) / SR
    L, R = np.zeros(n), np.zeros(n)
    for m in midis:
        f0 = mtof(m)
        for v, dc in enumerate((-6.0, 0.0, 6.0)):
            vib = 5.0 * np.sin(2 * np.pi * (5.0 + rng.uniform(-0.4, 0.4)) * t + rng.uniform(0, 2 * np.pi))
            drift = 2.0 * np.sin(2 * np.pi * 0.13 * t + rng.uniform(0, 2 * np.pi))
            phase = 2 * np.pi * f0 * np.cumsum(2.0 ** ((dc + vib + drift) / 1200.0)) / SR + rng.uniform(0, 2 * np.pi)
            s = np.zeros(n)
            for k in range(1, 11):
                if k * f0 > 6000:
                    break
                s += (1.0 / k) / (1.0 + (k * f0 / 1100.0) ** 2) * np.sin(k * phase)
            gl, gr = pan_gains((0.25, 0.5, 0.75)[v])
            L += gl * s
            R += gr * s
    env = np.ones(n)
    na = min(n, int(attack * SR))
    env[:na] = np.sin(np.linspace(0, np.pi / 2, na)) ** 2
    h = min(n, int(dur * SR))
    env[h:] *= np.cos(np.linspace(0, np.pi / 2, n - h)) ** 2
    return np.stack([L * env, R * env], axis=1) / (3 * len(midis))


def reverb_ir(rng, length: float = 2.9, predelay: float = 0.020):
    """Stereo synthetic IR: early reflections + exponentially decaying noise, darker as it decays."""
    n = int(length * SR)
    t = np.arange(n) / SR
    f = np.fft.rfftfreq(n, 1 / SR)
    lf = np.log2(np.maximum(f, 1.0))
    edges, rt60 = (0, 300, 1200, 4000, SR / 2), (2.2, 2.0, 1.45, 0.85)
    ir = np.zeros((n, 2))
    for ch in range(2):
        X = np.fft.rfft(rng.standard_normal(n))
        tail = np.zeros(n)
        for b in range(4):
            m = np.ones_like(f)
            if edges[b] > 0:
                m *= 0.5 * (1 + np.tanh((lf - np.log2(edges[b])) * 4))
            if edges[b + 1] < SR / 2:
                m *= 0.5 * (1 - np.tanh((lf - np.log2(edges[b + 1])) * 4))
            tail += np.fft.irfft(X * m, n) * np.exp(-6.9078 * t / rt60[b])
        tail *= 1 - np.exp(-t / 0.015)
        er = np.zeros(n)
        for j, dl in enumerate((0.0071, 0.0113, 0.0167, 0.0229, 0.0291, 0.0373, 0.0457, 0.0569)):
            er[int(dl * (1.0 + 0.07 * (ch * 2 - 1) * ((j % 3) - 1)) * SR)] += 0.75 ** j * (1 if (j + ch) % 2 == 0 else -1)
        ir[:, ch] = 0.85 * tail / np.sqrt(np.sum(tail ** 2)) + 0.35 * er / np.sqrt(np.sum(er ** 2))
    ir = np.concatenate([np.zeros((int(predelay * SR), 2)), ir])
    return ir / np.sqrt(np.sum(ir ** 2) / 2)


def fft_convolve(x, h):
    """Linear convolution of 1-D x and h (overlap-add for long inputs)."""
    n = len(x) + len(h) - 1
    nfft = 1 << (2 * len(h) - 1).bit_length()
    nfft = max(nfft, 1 << 20)
    step = nfft - len(h) + 1
    H = np.fft.rfft(h, nfft)
    y = np.zeros(n)
    for s in range(0, len(x), step):
        blk = x[s:s + step]
        yb = np.fft.irfft(np.fft.rfft(blk, nfft) * H, nfft)[:len(blk) + len(h) - 1]
        y[s:s + len(yb)] += yb
    return y


def zero_phase_eq(x, hp_hz: float = 30.0, shelf_hz: float = 150.0, shelf_db: float = -6.0):
    """2nd-order high-pass magnitude + first-order-like low shelf, applied with zero phase (FFT)."""
    nfft = 1 << (len(x) + SR).bit_length()
    X = np.fft.rfft(x, nfft, axis=0)
    f = np.fft.rfftfreq(nfft, 1 / SR)
    hp = 1.0 / np.sqrt(1.0 + (hp_hz / np.maximum(f, 1e-3)) ** 4)
    hp[0] = 0.0
    g = 10 ** (shelf_db / 20)
    shelf = g + (1 - g) * (f ** 2 / (f ** 2 + shelf_hz ** 2))
    return np.fft.irfft(X * (hp * shelf)[:, None], nfft, axis=0)[: len(x)]


# ------------------------------------------------------------------ composition
def compose(duration: float, pc: int, minor: bool, rng) -> dict:
    bpm, n_bars, tail = fit_tempo(duration)
    beat = 60.0 / bpm
    bar = 4 * beat
    deg = MINOR_DEG if minor else MAJOR_DEG
    bars = []
    for k, name in enumerate(progression(n_bars, minor, rng)):
        off, q = deg[name]
        root = (pc + off) % 12
        if k == n_bars - 1 and k > 0:  # cadence bar: sus4 resolving to the plain chord
            segs = [(0.0, 2.0, {"root": root, "q": "sus4", "color": None}),
                    (2.0, 4.0, {"root": root, "q": q, "color": None})]
        else:
            color = None
            if k > 0 and q == "M" and name in ("VI", "IV") and rng.random() < 0.5:
                color = "maj7"
            elif k > 0 and q == "m" and rng.random() < 0.35:
                color = "7"
            segs = [(0.0, 4.0, {"root": root, "q": q, "color": color})]
        bars.append(segs)
    final = {"root": pc, "q": "m" if minor else "M", "color": "add9"}
    t_final = n_bars * bar

    def dyn(k):
        return 0.88 + 0.12 * math.sin(math.pi * (k + 0.5) / (n_bars + 1))

    piano, pads = [], []  # piano: (t, midi, vel, hold, release or None); pads: (t0, t1, midis)
    prev_bass = prev_pad = None
    for k, segs in enumerate(bars):
        t_bar = k * bar
        for b0, b1, ch in segs:
            ch["bass"] = prev_bass = pick_bass(ch, prev_bass)
            ch["lh"] = lh_notes(ch["bass"], ch)
            prev_pad = pad_voicing(ch, prev_pad)
            pads.append((max(0.0, t_bar + b0 * beat - 0.15), t_bar + b1 * beat, prev_pad))
        for j in range(8):
            b0, b1, ch = next(s for s in segs if s[0] <= j / 2 < s[1])
            t = max(0.0, t_bar + j * beat / 2 + (0.0 if k == j == 0 else rng.normal(0, 0.004)))
            vel = LH_VEL[j] * dyn(k) * (1 + rng.normal(0, 0.04))
            piano.append((t, ch["lh"][(j - int(2 * b0)) % 8], vel, max(0.05, t_bar + b1 * beat - t - 0.012), None))
        if k == 0 and segs[0][2]["bass"] - 12 >= 28:
            piano.append((0.004, segs[0][2]["bass"] - 12, 0.30 * dyn(0), bar - 0.02, None))

    lo, hi = melody_range(pc)
    sc = [m for m in range(lo, hi + 1) if (m - pc) % 12 in (MINOR_SCALE if minor else MAJOR_SCALE)]
    tonic_tones, third_f = chord_tones(final)
    center = (lo + hi) / 2.0
    prev = min((m for m in range(lo, hi + 1) if m % 12 in tonic_tones), key=lambda m: abs(m - center - 1))
    melody = []
    for k, segs in enumerate(bars):
        p = k % 4
        cadence = len(segs) == 2
        if cadence:
            rhythm = ((0, 2), (2, 2))
        elif p == 3:
            rhythm = END_RHYTHMS[int(rng.integers(len(END_RHYTHMS)))]
        else:
            rhythm = RHYTHMS[int(rng.integers(len(RHYTHMS)))]
        target = center - 1.0 + ARC[p] + 2.0 * math.sin(math.pi * (k + 0.5) / (n_bars + 1))
        for b0, dur in rhythm:
            ch = next(s for s in segs if s[0] <= b0 < s[1])[2]
            tones, third = chord_tones(ch)
            if cadence:  # 4-3 suspension: sus tone, then the third
                want = (ch["root"] + (5 if ch["q"] == "sus4" else third)) % 12
                note = min((m for m in range(lo, hi + 1) if m % 12 == want), key=lambda m: abs(m - prev))
            elif b0 in (0, 2) or dur >= 2:  # strong beat: chord tone, small step, towards the arc target
                note = min((m for m in range(lo, hi + 1) if m % 12 in tones),
                           key=lambda m: abs(m - prev) + 0.35 * abs(m - target) + (2.5 if m == prev else 0.0)
                           + 0.8 * rng.random())
            else:  # weak beat: passing / neighbour scale tone
                i = min(range(len(sc)), key=lambda q: abs(sc[q] - prev))
                direction = 1 if target > prev else (-1 if target < prev else (1 if rng.random() < 0.5 else -1))
                note = sc[int(np.clip(i + direction * (1 if rng.random() < 0.75 else 2), 0, len(sc) - 1))]
            t = k * bar + b0 * beat + 0.012 + rng.normal(0, 0.005)
            vel = (0.47 if b0 == 0 else 0.40) * dyn(k) * (1 + rng.normal(0, 0.04))
            melody.append((t, note, vel, dur * beat * 0.96, 0.30))
            prev = note

    # final chord: rolled tonic add9 (left hand), tonic + third in the melody, all ringing to the end
    R = 40 + (pc - 40) % 12
    for j, m in enumerate((R, R + 7, R + 12, R + 14, R + 12 + third_f)):
        t = t_final + j * beat / 2 + (rng.normal(0, 0.004) if j else 0.0)
        piano.append((t, m, LH_VEL[j] * dyn(n_bars) * 0.95, max(0.05, duration - t), None))
    if R - 12 >= 28:
        piano.append((t_final + 0.004, R - 12, 0.30 * dyn(n_bars), max(0.05, duration - t_final), None))
    top = min((m for m in range(lo, hi + 1) if m % 12 in tonic_tones),
              key=lambda m: abs(m - prev) + (0.0 if m % 12 == pc else 1.5))
    t = t_final + 0.012
    melody.append((t, top, 0.44 * dyn(n_bars), max(0.05, duration - t), 0.30))
    above = [m for m in range(top + 3, top + 5) if m % 12 in tonic_tones]
    if above:
        melody.append((t + 0.02, above[0], 0.36 * dyn(n_bars), max(0.05, duration - t), 0.30))
    pads.append((max(0.0, t_final - 0.15), duration + 0.3, pad_voicing(final, prev_pad)))
    chords = [" ".join(chord_label(s[2]) for s in segs) for segs in bars] + [chord_label(final)]
    return {"bpm": bpm, "bars": n_bars, "tail": tail, "t_final": t_final, "chords": chords,
            "piano": piano, "melody": melody, "pads": pads}


def render(duration: float, seed: int, key: str):
    pc, minor, label = parse_key(key)
    rng = np.random.default_rng(seed)
    comp = compose(duration, pc, minor, rng)
    ns = ac.samples_for(duration)
    total = ns + 2 * SR
    piano = Piano(seed)
    planned = []
    for t, m, vel, hold, rel in comp["piano"] + comp["melody"]:
        rel = rel if rel is not None else (0.22 if mtof(m) < 130 else 0.16)
        k, n = piano.plan(m, vel, hold, rel, int(rng.integers(2)))
        planned.append((t, m, vel, hold, rel, k, n))
    piano.build()
    buf = np.zeros((total, 2))
    for t, m, vel, hold, rel, k, n in planned:
        i0 = int(round(t * SR))
        if i0 >= total:
            continue
        sig = piano.render(k, n, vel, hold, rel)[: total - i0]
        gl, gr = pan_gains(pitch_pan(m))
        buf[i0:i0 + len(sig), 0] += gl * sig
        buf[i0:i0 + len(sig), 1] += gr * sig
    pad = np.zeros((total, 2))
    for t0, t1, midis in comp["pads"]:
        sig = pad_chord(midis, t1 - t0, rng)
        i0 = int(round(t0 * SR))
        n = min(len(sig), total - i0)
        if n > 0:
            pad[i0:i0 + n] += sig[:n]

    def rms(x):
        return float(np.sqrt(np.mean(x ** 2)))

    pad *= rms(buf) / max(rms(pad), 1e-12) * 10 ** (-16.0 / 20)  # very light string pad
    dry = buf + pad
    ir = reverb_ir(rng)
    mid = dry.mean(axis=1)
    wet = np.stack([fft_convolve(mid, ir[:, 0]), fft_convolve(mid, ir[:, 1])], axis=1)[:total]
    wet *= rms(dry) / max(rms(wet), 1e-12) * 10 ** (-8.0 / 20)
    mix = zero_phase_eq((dry + wet)[:ns])
    mix -= mix.mean(axis=0)
    g = np.ones(ns)
    nf = min(int(FADE * SR), ns // 2)
    g[:nf] = np.sin(np.pi / 2 * np.arange(nf) / nf) ** 2
    g[ns - nf:] = np.cos(np.pi / 2 * np.arange(1, nf + 1) / nf) ** 2
    mix *= g[:, None]
    mix *= 10 ** (PEAK_DBFS / 20) / max(float(np.abs(mix).max()), 1e-12)
    if not np.isfinite(mix).all():
        raise RuntimeError("non-finite BGM samples")
    meta = {"seed": int(seed), "key": label, "bpm": comp["bpm"], "bars": comp["bars"],
            "final_chord_at": round(comp["t_final"], 3), "tail_s": round(comp["tail"], 3),
            "chords": comp["chords"], "notes": len(planned), "duration": duration, "samples": ns,
            "peak_dbfs": round(ac.db(np.abs(mix).max()), 2), "rms_dbfs": round(ac.db(rms(mix)), 2),
            "dc": [float(f"{v:.2e}") for v in mix.mean(axis=0)]}
    return mix, meta


def write_for_project(d, seed=None, key=None) -> dict:
    """Render audio/bgm_48k.wav for the project's duration. seed/key default to the previous run's
    (audio/bgm_48k.json), then crc32(slug) / Am."""
    d = ac.project_dir(d)
    proj = ac.load_project(d)
    if not proj.get("duration"):
        raise SystemExit("project.json has no duration yet: run narrate.py first")
    duration = float(proj["duration"])
    out = d / "audio" / "bgm_48k.wav"
    prev = {}
    if out.with_suffix(".json").is_file():
        try:
            old = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
            prev = {"seed": old.get("seed"), "key": old.get("key")}
        except (ValueError, OSError):
            prev = {}
    if seed is None:
        seed = prev.get("seed")
    if seed is None:
        seed = zlib.crc32(str(proj.get("slug") or d.name).encode("utf-8")) & 0x7FFFFFFF
    key = key or prev.get("key") or "Am"
    t0 = time.time()
    mix, meta = render(duration, int(seed), key)
    ac.write_wav(out, mix, bits=24)
    st = ac.ebur128(mix)
    meta.update({"I_lufs": round(st["I"], 2), "tp_dbtp": round(st["TP"], 2),
                 "created": time.strftime("%Y-%m-%d %H:%M:%S")})
    ac.atomic_write_text(out.with_suffix(".json"), json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
    ac.update_project(d, audio={"bgm": "audio/bgm_48k.wav"})
    print(f"bgm: key {meta['key']}, seed {meta['seed']}, {meta['bpm']} BPM, {meta['bars']} bars + final chord at "
          f"{meta['final_chord_at']:.2f}s (rings {meta['tail_s']:.2f}s)")
    print("     " + " | ".join(meta["chords"]))
    print(f"     {duration:.6f}s = {meta['samples']} samples, peak {meta['peak_dbfs']} dBFS, TP {st['TP']:.2f} dBTP, "
          f"I {st['I']:.1f} LUFS, rms {meta['rms_dbfs']} dBFS, DC {meta['dc']}, {time.time() - t0:.1f}s")
    print(f"wrote {out}")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, help="project directory containing project.json")
    ap.add_argument("--seed", type=int, help="default: previous run's seed, else crc32(slug)")
    ap.add_argument("--key", help="default: previous run's key, else Am")
    args = ap.parse_args()
    if args.key:
        parse_key(args.key)
    write_for_project(args.project, args.seed, args.key)


if __name__ == "__main__":
    main()
