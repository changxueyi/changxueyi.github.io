# -*- coding: utf-8 -*-
"""Shared helpers for the textbook-reading-video pipeline (no secrets, no Blender)."""
import json, os, subprocess, tempfile

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANNOT = set("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳®©*＊")
PUNCT = set("，。、；：！？…—·“”‘’「」『』《》（）()\"',.;:!?~～ 　")
FINAL = set("。！？…")
CLOSE = set("”’」』）)")
OPEN = set("“‘「『（(《")

def load_project(root):
    with open(os.path.join(root, "project.json"), encoding="utf-8") as f:
        return json.load(f)

def save_project(root, cfg):
    """atomic write; callers pass the full dict they loaded (other keys preserved)"""
    path = os.path.join(root, "project.json")
    fd, tmp = tempfile.mkstemp(dir=root, prefix=".project.", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)

def update_project(root, **kv):
    cfg = load_project(root)
    cfg.update(kv)
    save_project(root, cfg)
    return cfg

def ocr_bin():
    env = os.environ.get("TBV_OCR")
    if env and os.path.exists(env):
        return env
    out = subprocess.run([os.path.join(SKILL, "scripts", "ensure_ocr.sh")], capture_output=True, text=True, check=True)
    return out.stdout.strip().splitlines()[-1]

def run_ocr(paths, chars=True):
    cmd = [ocr_bin()] + (["--chars"] if chars else []) + list(paths)
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return [json.loads(l) for l in out.splitlines() if l.strip()]

def ocr_lines(d, min_conf=0.0, merge=True):
    """Vision JSON -> lines in pixel space (top-left origin) sorted top->bottom, left->right.
    each line: {t, x0, y0, x1, y1, h, c, chars:[(ch, x0, x1)]}
    merge=False keeps the raw OCR items (a TOC row may hold several unrelated items)."""
    W, H = d["W"], d["H"]
    lines = []
    for it in d["items"]:
        if it["c"] < min_conf:
            continue
        x0 = it["x"] * W; y0 = (1 - it["y"] - it["h"]) * H
        ln = {"t": it["t"], "x0": x0, "y0": y0, "x1": x0 + it["w"] * W, "y1": y0 + it["h"] * H,
              "h": it["h"] * H, "c": it["c"], "chars": []}
        for ch, bb in zip(it["t"], it.get("chars") or [[]] * len(it["t"])):
            if bb:
                ln["chars"].append((ch, bb[0] * W, (bb[0] + bb[2]) * W))
            else:
                ln["chars"].append((ch, None, None))
        # fill missing char boxes by interpolation across the line box
        n = len(ln["chars"])
        for k, (ch, a, b) in enumerate(ln["chars"]):
            if a is None:
                a = x0 + (ln["x1"] - x0) * k / max(n, 1); b = x0 + (ln["x1"] - x0) * (k + 1) / max(n, 1)
                ln["chars"][k] = (ch, a, b)
        lines.append(ln)
    # merge items that sit on the same text row (OCR may split a row around pictures)
    lines.sort(key=lambda l: (l["y0"] + l["y1"]) / 2)
    if not merge:
        return lines
    rows = []
    for ln in lines:
        cy = (ln["y0"] + ln["y1"]) / 2
        if rows and abs(cy - rows[-1]["cy"]) < 0.45 * min(ln["h"], rows[-1]["h"]):
            rows[-1]["items"].append(ln)
            rows[-1]["cy"] = (rows[-1]["cy"] + cy) / 2
        else:
            rows.append({"cy": cy, "h": ln["h"], "items": [ln]})
    out = []
    for r in rows:
        its = sorted(r["items"], key=lambda l: l["x0"])
        chars = [c for l in its for c in l["chars"]]
        out.append({"t": "".join(l["t"] for l in its), "x0": its[0]["x0"], "x1": max(l["x1"] for l in its),
                    "y0": min(l["y0"] for l in its), "y1": max(l["y1"] for l in its),
                    "h": sorted(l["h"] for l in its)[len(its) // 2], "c": min(l["c"] for l in its), "chars": chars})
    return out

def text_len(s):
    return sum(1 for ch in s if ch not in PUNCT and ch not in ANNOT)
