#!/usr/bin/env python3
"""Paper-colour gradient that sits behind the captions (RGBA PNG, 1920x1080 by default).

usage: make_bottom_fade.py [--project DIR | --out PATH] [--y0 770] [--y1 905] [--amax 0.90] [--color F5F1E9]

Alpha is 0 above y0, rises with a smoothstep to amax at y1 and stays at amax down to the bottom edge.
Default output: DIR/post/bottom_fade.png with --project (compose.py uses that file and creates it with these
defaults when it is missing), otherwise ./bottom_fade.png.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from post_common import W, H, PostError, run_main  # noqa: E402

DEFAULTS = dict(y0=770.0, y1=905.0, amax=0.90, color="F5F1E9")


def parse_color(c):
    c = c.strip().lstrip("#")
    if len(c) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in c):
        raise PostError(f"colour must be RRGGBB hex, got {c!r}")
    return [int(c[i:i + 2], 16) for i in (0, 2, 4)]


def make_fade(out, y0=DEFAULTS["y0"], y1=DEFAULTS["y1"], amax=DEFAULTS["amax"], color=DEFAULTS["color"],
              width=W, height=H):
    """Write the mask and return a one-line description."""
    import numpy as np
    from PIL import Image
    if not (y1 > y0 and 0.0 <= amax <= 1.0):
        raise PostError(f"need y1 > y0 and 0 <= amax <= 1 (got y0={y0}, y1={y1}, amax={amax})")
    y = np.arange(height, dtype=np.float64) + 0.5            # pixel-centre rows
    u = np.clip((y - y0) / (y1 - y0), 0.0, 1.0)
    alpha = amax * u * u * (3.0 - 2.0 * u)                    # smoothstep
    img = np.zeros((height, width, 4), np.uint8)
    img[..., :3] = parse_color(color)
    img[..., 3] = np.round(alpha * 255.0).astype(np.uint8)[:, None]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    tmp = out + ".tmp.png"
    Image.fromarray(img, "RGBA").save(tmp)
    os.replace(tmp, out)
    col = img[:, 0, 3]
    nz = np.nonzero(col)[0]
    first = int(nz[0]) if len(nz) else None
    return (f"{out}: {width}x{height} #{color.lstrip('#').upper()} y0={y0:g} y1={y1:g} amax={amax:g}; "
            f"first visible row {first}, alpha/255 at rows 850/905/1079 = "
            f"{col[min(850, height - 1)]}/{col[min(905, height - 1)]}/{col[height - 1]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", metavar="DIR", help="write DIR/post/bottom_fade.png")
    ap.add_argument("--out", metavar="PATH", help="output PNG (overrides --project)")
    ap.add_argument("--y0", type=float, default=DEFAULTS["y0"], help="last fully transparent row (default 770)")
    ap.add_argument("--y1", type=float, default=DEFAULTS["y1"], help="row where alpha reaches amax (default 905)")
    ap.add_argument("--amax", type=float, default=DEFAULTS["amax"], help="maximum opacity 0-1 (default 0.90)")
    ap.add_argument("--color", default=DEFAULTS["color"], help="RRGGBB paper colour (default F5F1E9)")
    ap.add_argument("--size", default=f"{W}x{H}", help="WxH (default 1920x1080)")
    a = ap.parse_args()
    try:
        width, height = (int(v) for v in a.size.lower().split("x"))
    except ValueError:
        raise PostError(f"--size must look like 1920x1080, got {a.size!r}") from None
    if a.out:
        out = os.path.abspath(os.path.expanduser(a.out))
    elif a.project:
        out = os.path.join(os.path.abspath(os.path.expanduser(a.project)), "post", "bottom_fade.png")
    else:
        out = os.path.abspath("bottom_fade.png")
    print("wrote", make_fade(out, a.y0, a.y1, a.amax, a.color, width, height))
    return 0


if __name__ == "__main__":
    run_main(main)
