#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turn an illustration / photo into a grayscale paper-cut card PNG (RGBA) for the floating card layer.

  prep_card.py IN.png OUT.png [--mode cutout|card] [--levels 5] [--tol 30] [--max 1024] [--border 6]

cutout: removes the background connected to the image border (colour close to the border median, or
        existing transparency), posterises to a few grey levels and adds a white paper rim.
card:   keeps the whole picture inside a rounded white paper card (use for photos / busy backgrounds).
Prints OUT and its size; use the aspect for the card "w"/"h" in project.json.
"""
import argparse
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

def bg_mask(rgb, alpha, tol):
    """True where background: transparent, or colour-close to the border and connected to it"""
    h, w, _ = rgb.shape
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    ref = np.median(border, axis=0)
    close = np.sqrt(((rgb - ref) ** 2).sum(-1)) < tol
    if alpha is not None:
        close |= alpha < 20
    lab = Image.fromarray((close * 255).astype(np.uint8)).copy()   # writable copy (fromarray may share a read-only buffer)
    for x, y in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
        if lab.getpixel((x, y)) == 255:
            ImageDraw.floodfill(lab, (x, y), 128)
    return np.asarray(lab) == 128

def posterise(gray, levels):
    g = np.asarray(ImageOps.autocontrast(gray, cutoff=1)).astype(np.float32) / 255.0
    q = np.round(g * (levels - 1)) / (levels - 1)
    return (0.12 + 0.80 * q) * 255.0          # keep it paper-like: no pure black / white

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--mode", choices=["cutout", "card"], default="cutout")
    ap.add_argument("--levels", type=int, default=5)
    ap.add_argument("--tol", type=float, default=30.0)
    ap.add_argument("--max", type=int, default=1024)
    ap.add_argument("--border", type=int, default=6, help="white rim width in px (cutout)")
    a = ap.parse_args()
    im = Image.open(a.src)
    im = ImageOps.exif_transpose(im)
    im.thumbnail((a.max, a.max), Image.LANCZOS)
    rgba = im.convert("RGBA")
    arr = np.asarray(rgba).astype(np.float32)
    rgb, alpha = arr[..., :3], (arr[..., 3] if im.mode in ("RGBA", "LA", "P") else None)
    grey = posterise(rgba.convert("L"), a.levels)
    pad = 4 * a.border + 8
    if a.mode == "cutout":
        bg = bg_mask(rgb, alpha, a.tol)
        fg = Image.fromarray((~bg * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(5))
        fg = ImageOps.expand(fg, pad, 0)
        rim = fg.filter(ImageFilter.MaxFilter(2 * a.border + 1)).filter(ImageFilter.GaussianBlur(1.2))
        g = ImageOps.expand(Image.fromarray(grey.astype(np.uint8)), pad, 245)
        fga = np.asarray(fg.filter(ImageFilter.GaussianBlur(0.8))).astype(np.float32) / 255.0
        col = np.asarray(g).astype(np.float32) * fga + 246.0 * (1 - fga)     # white rim under the cut
        out = np.dstack([col, col, col * 0.985, np.asarray(rim).astype(np.float32)])
    else:
        w, h = rgba.size
        m = max(8, int(0.05 * min(w, h)))
        card = Image.new("L", (w + 2 * m, h + 2 * m), 0)
        ImageDraw.Draw(card).rounded_rectangle([0, 0, w + 2 * m - 1, h + 2 * m - 1], radius=2 * m, fill=255)
        col = np.full((h + 2 * m, w + 2 * m), 246.0, np.float32)
        col[m:m + h, m:m + w] = grey
        out = np.dstack([col, col, col * 0.985, np.asarray(card).astype(np.float32)])
    res = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")
    bb = res.getchannel("A").getbbox()
    if bb:
        res = res.crop(bb)
    res.save(a.dst, optimize=True)
    print(a.dst, res.size[0], res.size[1], f"aspect h/w = {res.size[1] / res.size[0]:.3f}")

if __name__ == "__main__":
    main()
