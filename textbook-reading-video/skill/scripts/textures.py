# -*- coding: utf-8 -*-
"""Texture preparation: HD text pages (de-fringe, flatten lighting, 3x), colour pages (2x), fillers, endpaper."""
import os, difflib
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SONGTI = "/System/Library/Fonts/Supplemental/Songti.ttc"

def to_png(src, dst):
    im = Image.open(src)
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        im = im.convert("RGBA"); bg.paste(im, mask=im.split()[-1]); im = bg
    im.convert("RGB").save(dst)

def size(p):
    return Image.open(p).size

def colour_page(src, dst, scale=2):
    im = Image.open(src).convert("RGB")
    im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
    im.filter(ImageFilter.UnsharpMask(radius=1.5, percent=50, threshold=2)).save(dst, optimize=True)

def _flatten(lum):
    """divide by a local paper-brightness estimate (removes uneven lighting of phone photos)"""
    h, w = lum.shape
    small = Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8)).resize((max(8, w // 4), max(8, h // 4)), Image.BILINEAR)
    bgd = small.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(6)).resize((w, h), Image.BILINEAR)
    bg = np.maximum(np.asarray(bgd).astype(np.float32), 60.0)
    return np.clip(lum / bg * 250.0, 0, 255)

def text_page(src, dst, scale=3, clean=True):
    """screenshots / scans of printed pages: remove sub-pixel colour fringes, keep solid colour areas"""
    a = np.asarray(Image.open(src).convert("RGB")).astype(np.float32)
    lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    if clean:
        lum = _flatten(lum)
    sat = a.max(2) - a.min(2)
    solid = Image.fromarray(((sat > 60) * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(7))
    solid = np.asarray(solid) > 0
    out = np.repeat(lum[..., None], 3, axis=2)
    out[solid] = a[solid]
    im = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).resize((a.shape[1] * scale, a.shape[0] * scale), Image.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=2.0, percent=80, threshold=2))
    b = np.asarray(im).astype(np.float32)
    l2 = b.mean(2, keepdims=True)
    paper = np.clip((l2 - 200.0) / 45.0, 0, 1)          # >=245 -> pure paper white
    ink = 255.0 * (np.clip(b, 0, 255) / 255.0) ** 1.15
    b = ink * (1 - paper) + 255.0 * paper
    Image.fromarray(np.clip(b, 0, 255).astype(np.uint8)).save(dst, optimize=True)

def layout_from_lines(lines, px):
    """margins / line pitch of the reading page, in original pixels"""
    W, H = px
    ls = [l for l in lines if len(l["t"]) >= 10]
    if len(ls) < 3:
        return {"left": 0.074 * W, "right": 0.956 * W, "top": 0.058 * H, "pitch": 0.0296 * H, "font": 0.026 * H}
    ys = sorted(l["y0"] for l in ls)
    pitches = sorted(b - a for a, b in zip(ys, ys[1:]) if b - a > 0.5 * ls[0]["h"])
    pitch = pitches[len(pitches) // 2] if pitches else 0.0296 * H
    x0s = sorted(l["x0"] for l in ls); x1s = sorted(l["x1"] for l in ls)
    hs = sorted(l["h"] for l in ls)
    return {"left": x0s[len(x0s) // 5], "right": x1s[-max(1, len(x1s) // 5)], "top": ys[0], "pitch": pitch,
            "font": hs[len(hs) // 2] * 0.92}

def _songti(size):
    for i in range(12):
        try:
            f = ImageFont.truetype(SONGTI, size, index=i)
        except Exception:
            break
        if f.getname() == ("Songti SC", "Regular"):
            return f
    return ImageFont.truetype(SONGTI, size)

def make_fillers(tex_dir, corpus, lay, px, n=4, scale=3):
    """fake text pages for the fast riffle, same layout as the reading page"""
    W, H = px[0] * scale, px[1] * scale
    corpus = "".join(ch for ch in corpus if not ch.isspace()) or "春天来了，万物复苏。"
    font = _songti(max(12, int(lay["font"] * scale)))
    small = _songti(max(10, int(lay["font"] * scale * 0.6)))
    cw = lay["font"] * scale * 1.02
    per = max(10, int((lay["right"] - lay["left"]) * scale // cw))
    nlines = max(8, int((H * 0.9 - lay["top"] * scale) // (lay["pitch"] * scale)))
    out = []
    for k in range(n):
        img = Image.new("RGB", (W, H), (255, 255, 255)); d = ImageDraw.Draw(img)
        off = (k * 977) % max(1, len(corpus))
        text = (corpus[off:] + corpus[:off]) * 4
        for i in range(nlines):
            seg = text[i * per:(i + 1) * per]
            if i % 9 == 0:
                seg = "\u3000\u3000" + seg[:-2]
            for j, ch in enumerate(seg):
                d.text((lay["left"] * scale + j * cw, lay["top"] * scale + i * lay["pitch"] * scale), ch, font=font, fill=(24, 22, 22))
        d.text((W / 2, H * 0.965), str(70 + k), font=small, fill=(40, 40, 40), anchor="mm")
        p = f"filler_{k + 1}.png"
        img.save(os.path.join(tex_dir, p), optimize=True)
        out.append("textures/" + p)
    return out

def endpaper(dst, size=2048):
    rng = np.random.default_rng(3)
    base = np.array([239, 230, 210], np.float32)
    noise = rng.normal(0, 1.6, (size, size, 1)).astype(np.float32)
    Image.fromarray(np.clip(base + noise, 0, 255).astype(np.uint8)).save(dst, optimize=True)

def _same_row(a, b):
    return abs((a["y0"] + a["y1"]) / 2 - (b["y0"] + b["y1"]) / 2) < 0.45 * min(a["h"], b["h"])

def find_toc_entry(items, title):
    """TOC entry that contains the article title -> highlight box (px).
    items = raw OCR items (ocr_lines(..., merge=False)); the box runs from the entry
    to the page number on the same row, ignoring unit headings further left."""
    title = "".join(ch for ch in title if not ch.isspace())
    if not title:
        return None
    best, br = None, 0.0
    for l in items:
        t = l["t"]
        if title in t:
            r = 1.0
        else:
            m = difflib.SequenceMatcher(None, t, title, autojunk=False).find_longest_match(0, len(t), 0, len(title))
            r = m.size / max(1, len(title))
        right = [o for o in items if o is not l and _same_row(o, l) and o["x0"] >= l["x1"] - 2]
        if any(o["t"].strip().isdigit() for o in right):
            r += 0.1                      # an entry with a page number beats a heading
        if r > br:
            best, br = l, r
    if best is None or br < 0.6:
        return None
    x1 = max([best["x1"]] + [o["x1"] for o in items if o is not best and _same_row(o, best) and o["x0"] >= best["x1"] - 2])
    return {"line_top": round(best["y0"] - 1, 1), "line_h": round(best["h"], 1),
            "x0": round(max(0.0, best["x0"] - 8), 1), "x1": round(x1 + 4, 1)}
