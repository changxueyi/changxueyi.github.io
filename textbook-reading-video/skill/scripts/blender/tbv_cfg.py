# -*- coding: utf-8 -*-
# Project-driven constants and helpers. exec'd inside Blender by build_scene.py into one shared
# namespace (tbv_cfg -> tbv_materials -> tbv_book -> tbv_camlight -> tbv_overlays -> tbv_cards -> tbv_verify).
# Needs PROJECT_DIR in the namespace.
import math, json, os

with open(os.path.join(PROJECT_DIR, "project.json"), encoding="utf-8") as _f:
    PROJ = json.load(_f)
P = os.path.abspath(PROJECT_DIR)
FPS = int(PROJ.get("fps", 30))
TL = PROJ["timeline"]                       # [{i, text, start, end}] from narrate.py
DURATION = float(PROJ["duration"])
NFRAMES = int(round(DURATION * FPS))
READING = {int(r["i"]): r for r in PROJ["reading"]}
PAGES = PROJ["pages"]

def fr(t):
    """seconds -> (float) frame number, frame 1 == t 0.0"""
    return 1.0 + t * FPS

def ab(rel):
    if not rel:
        return None
    p = rel if os.path.isabs(rel) else os.path.join(P, rel)
    return p if os.path.exists(p) else None

def tex(role):
    pg = PAGES.get(role)
    return ab(pg.get("tex") or pg.get("src")) if pg else None

FILLERS = [ab(f) for f in PROJ.get("fillers", [])] or [None]
while len(FILLERS) < 4:
    FILLERS.append(FILLERS[len(FILLERS) % max(1, len(FILLERS))])
ENDPAPER = ab(PROJ.get("endpaper"))

# ---------------- book geometry (metres) ----------------
W = float(PROJ["book"]["W"]); H = float(PROJ["book"]["H"])
BT = 0.0025                 # board thickness
OV = 0.003                  # board overhang
H_REF = 0.010               # reference block thickness used by shape keys
T0 = 0.010                  # closed page-block thickness (all pages on the right)
HL_END, HR_END = 0.004, 0.006
HL_START = 0.0003
LAM = 0.006                 # gutter curvature length
DOME, DROOP = 0.10, 0.10
PAGE_T = 0.00012            # paper thickness (Solidify)
NX, NZ = 72, 24             # page grid resolution
HL_LIFT = 0.002             # highlight bands float 2 mm above the paper

def clamp01(x):
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)

def smooth(x):
    x = clamp01(x)
    return x * x * x * (x * (6.0 * x - 15.0) + 10.0)

def smoothstep(e0, e1, x):
    return smooth((x - e0) / (e1 - e0)) if e1 != e0 else (1.0 if x >= e1 else 0.0)

def G(s):
    """page-block top profile (0 at the spine, ~1 across the page)"""
    s = max(0.0, min(W, s))
    u = clamp01((s - 0.86 * W) / (0.14 * W))
    sm = u * u * (3 - 2 * u)
    return (1.0 - math.exp(-s / LAM)) + DOME * math.sin(math.pi * s / W) - DROOP * sm

# ---------------- intro timeline (seconds, fixed: reading starts at intro_seconds = 5.4) ----------------
COVER_T = (1.00, 1.80)
COVER_PHI0 = math.radians(6.0)
RIFFLE_T = (3.30, 4.31)
HAS_TOC = bool(PAGES.get("toc")) and tex("toc") is not None
F = FILLERS
# name, t0, duration, front texture, back texture, eps_right, eps_left
TURNS = [
    ("P1", 1.90, 0.60, tex("title_page"), None, 0.00075, 0.00015),
    ("P2", 3.30, 0.62, tex("toc") if HAS_TOC else F[0], F[0] if HAS_TOC else F[1], 0.00060, 0.00030),
    ("F1", 3.43, 0.62, F[1], F[2], 0.00045, 0.00045),
    ("F2", 3.56, 0.62, F[3], F[0], 0.00030, 0.00060),
    ("PL", 3.69, 0.62, F[1], tex("left"), 0.00015, 0.00075),
]
EPS_L_LAST = TURNS[-1][6]
BASE_EPS = 0.00005

def gutter(t):
    return smoothstep(COVER_T[0], COVER_T[1], t)

def hR(t):
    return T0 + (HR_END - T0) * smoothstep(RIFFLE_T[0], RIFFLE_T[1], t)

def hL(t):
    return HL_START + (HL_END - HL_START) * smoothstep(RIFFLE_T[0], RIFFLE_T[1], t)

def turn_state(t, t0, dur):
    """returns (root angle, edge angle, u) for a page turning right->left"""
    u = clamp01((t - t0) / dur)
    th_e = math.pi * smooth(u / 0.85)
    th_r = math.pi * smooth((u - 0.15) / 0.85)
    return th_r, th_e, u

def cover_state(t):
    """front board angle phi (0 = closed on the right, pi = flat on the left) and hinge z"""
    k = smoothstep(COVER_T[0], COVER_T[1], t)
    phi = COVER_PHI0 + (math.pi - COVER_PHI0) * k
    zh = (BT + T0) + (BT - (BT + T0)) * k
    return phi, zh

# ---------------- page-space helpers ----------------
def page_px(role):
    pg = PAGES.get(role) or PAGES["right"]
    return pg["px"]

def page_xy(px, py, role="right"):
    """texture pixel (of the page's original image) -> world x, y on the open spread"""
    w, h = page_px(role)
    y = (0.5 - py / h) * H
    if role == "left":
        return (px / w - 1.0) * W, y
    return px / w * W, y

def page_z(x, role="right", t=1e9):
    """top surface height of the resting reading pages (right = static base page, left = back of PL)"""
    if role == "left":
        return BT + EPS_L_LAST + hL(t) * G(abs(x)) + PAGE_T
    return BT + BASE_EPS + hR(t) * G(abs(x))

def toc_z(x):
    """P2 (TOC) still resting on the right block before it turns"""
    return BT + TURNS[1][5] + T0 * G(x)

# ---------------- reading geometry + highlight schedule ----------------
BAND_TOP, BAND_BOT = 0.43, 0.98     # marker covers the lower part of the line box (like the reference)
AIM_DY = 0.0128                     # camera aims this far above the read line (line sits above the captions)

def _pages_used():
    cnt = {}
    for r in READING.values():
        for g in r.get("segments", []):
            cnt[g.get("page", "right")] = cnt.get(g.get("page", "right"), 0) + 1
    return cnt

_CNT = _pages_used()
READ_PAGE = max(_CNT, key=lambda k: (_CNT[k], k == "right")) if _CNT else "right"

def text_center_x(role):
    tb = (PROJ.get("text_block") or {}).get(role)
    if tb:
        return page_xy(0.5 * (tb[0] + tb[1]), 0, role)[0]
    return 0.5 * W if role != "left" else -0.5 * W

def text_width(role):
    tb = (PROJ.get("text_block") or {}).get(role)
    if tb:
        return abs(page_xy(tb[1], 0, role)[0] - page_xy(tb[0], 0, role)[0])
    return 0.88 * W

XC = {r: text_center_x(r) for r in ("left", "right")}
ZPS = {r: page_z(XC[r], r) for r in ("left", "right")}
ZP = ZPS[READ_PAGE]

def row_y(g):
    return page_xy(0, g["line_top"] + 0.5 * g["line_h"], g.get("page", "right"))[1]

def band_schedule():
    """[(i, j, seg, t0, t1, t_off)]: band j of sentence i grows linearly t0->t1, fades at t_off"""
    out = []
    for k, s in enumerate(TL):
        i = int(s["i"]); r = READING.get(i)
        if not r or not r.get("segments"):
            continue
        t_start = s["start"] + 0.03
        t_end = max(t_start + 0.2, s["end"] - 0.05)
        t_off = TL[k + 1]["start"] if k + 1 < len(TL) else s["end"] + 0.03
        segs = r["segments"]
        ws = [max(1e-6, float(g.get("weight", 1.0))) for g in segs]
        tcur = t_start
        for j, (g, w) in enumerate(zip(segs, ws)):
            dur = (t_end - t_start) * w / sum(ws)
            out.append((i, j, g, tcur, tcur + dur, t_off))
            tcur += dur
    return out

SCHED = band_schedule()
T_READ0 = TL[0]["start"] if TL else 5.4
T_READ1 = TL[-1]["end"] if TL else DURATION - 1.3

def sentence_times(i):
    for s in TL:
        if int(s["i"]) == int(i):
            return s["start"], s["end"]
    raise KeyError(f"sentence {i} not in timeline")

def char_time(i, page, line_top, cx):
    """time at which the highlight of sentence i reaches x = cx (px) on a row"""
    best = None
    for (si, j, g, t0, t1, toff) in SCHED:
        if si != int(i) or g.get("page", "right") != page:
            continue
        d = abs(g["line_top"] - line_top)
        if best is None or d < best[0]:
            best = (d, g, t0, t1)
    if best is None:
        return sentence_times(i)[0]
    _, g, t0, t1 = best
    u = clamp01((cx - g["x0"]) / max(1e-6, g["x1"] - g["x0"]))
    return t0 + (t1 - t0) * u

def find_word(word, sentence=None):
    """first occurrence of word in reading chars -> (sentence i, page, line_top, line_h, x0, x1)"""
    for i in sorted(READING):
        if sentence is not None and i != int(sentence):
            continue
        ch = READING[i].get("chars") or []
        s = "".join(c["c"] for c in ch)
        k = s.find(word)
        if k >= 0:
            a, b = ch[k], ch[k + len(word) - 1]
            if a["line_top"] == b["line_top"]:
                return i, a["page"], a["line_top"], a["line_h"], a["x0"], b["x1"]
            return i, a["page"], a["line_top"], a["line_h"], a["x0"], a["x1"]
    return None

def _target_at(t):
    """piecewise-constant reading target (x, y, z) of the row being highlighted at t"""
    cur = None
    for (i, j, g, t0, t1, toff) in SCHED:
        if t0 <= t or cur is None:
            cur = g
        if t0 > t:
            break
    if cur is None:
        return XC[READ_PAGE], 0.0, ZP
    pg = cur.get("page", "right")
    return XC[pg], row_y(cur) + AIM_DY, ZPS[pg]

def reading_target(t, win=2.0, lead=0.45, n=25):
    """Hann-window average of the row target, shifted ahead by `lead` s: the camera starts moving
    ~1.45 s before a new row is read and has settled ~0.55 s after"""
    acc = [0.0, 0.0, 0.0]; wsum = 0.0
    for k in range(n):
        u = k / (n - 1)
        w = 0.5 - 0.5 * math.cos(2 * math.pi * u) + 1e-3
        tt = min(max(t + lead + (u - 0.5) * win, T_READ0), T_READ1)
        p = _target_at(tt)
        for a in range(3):
            acc[a] += w * p[a]
        wsum += w
    return tuple(v / wsum for v in acc)
