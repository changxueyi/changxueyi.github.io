#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create a project from page images: copy sources, OCR, HD textures, riffle fillers, skeleton project.json.

  init_project.py --root DIR --slug beiying --cover c.png --left p74.png --right p75.png \
                  [--title-page t.png] [--toc toc.png] [--article-title 背影] [--title-text ...]
Only --cover and --right are required (a missing --left gets a generated text page).
"""
import argparse, json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tbv_common import run_ocr, ocr_lines, save_project, text_len
import textures as T

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--cover", required=True)
    ap.add_argument("--right", required=True)
    ap.add_argument("--left")
    ap.add_argument("--title-page")
    ap.add_argument("--toc")
    ap.add_argument("--article-title", default="")
    ap.add_argument("--title-text", default="那些长大后，才读懂的课文")
    ap.add_argument("--no-clean", action="store_true", help="skip illumination flattening of text pages")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    if os.path.exists(os.path.join(root, "project.json")):
        sys.exit(f"project already exists: {root}/project.json (use a new --root)")
    for d in ("src", "textures", "ocr", "audio", "render", "post", "out", "cards"):
        os.makedirs(os.path.join(root, d), exist_ok=True)
    roles = {"cover": a.cover, "title_page": a.title_page, "toc": a.toc, "left": a.left, "right": a.right}
    pages = {}
    for role, src in roles.items():
        if not src:
            pages[role] = None
            continue
        dst = os.path.join(root, "src", role + ".png")
        T.to_png(src, dst)
        pages[role] = {"src": f"src/{role}.png", "px": list(T.size(dst))}
    text_roles = [r for r in ("left", "right", "toc") if pages.get(r)]
    res = run_ocr([os.path.join(root, pages[r]["src"]) for r in text_roles], chars=True)
    for r, d in zip(text_roles, res):
        p = os.path.join(root, "ocr", r + ".json")
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        pages[r]["ocr"] = f"ocr/{r}.json"
    # textures
    for role in ("cover", "title_page"):
        if pages[role]:
            pages[role]["tex"] = f"textures/{role}_hd.png"
            T.colour_page(os.path.join(root, pages[role]["src"]), os.path.join(root, pages[role]["tex"]))
    for role in text_roles:
        pages[role]["tex"] = f"textures/{role}_hd.png"
        T.text_page(os.path.join(root, pages[role]["src"]), os.path.join(root, pages[role]["tex"]), clean=not a.no_clean)
    lines_r = ocr_lines(res[text_roles.index("right")], 0.3)
    layout = T.layout_from_lines(lines_r, pages["right"]["px"])
    corpus = "".join(l["t"] for r in text_roles if r != "toc" for l in ocr_lines(res[text_roles.index(r)], 0.5))
    fillers = T.make_fillers(os.path.join(root, "textures"), corpus, layout, pages["right"]["px"], n=4)
    if not pages["left"]:
        lp = os.path.join(root, "textures", "left_generated.png")
        shutil.copy(os.path.join(root, fillers[0]), lp)
        pages["left"] = {"src": None, "tex": "textures/left_generated.png", "px": pages["right"]["px"], "ocr": None}
    T.endpaper(os.path.join(root, "textures", "endpaper.png"))
    # book size: mean aspect of the real spread pages (both are mapped onto equal page meshes)
    asp = [pages[r]["px"][0] / pages[r]["px"][1] for r in ("left", "right") if pages[r] and pages[r].get("src")]
    H = 0.26; W = max(0.165, min(0.205, H * sum(asp) / len(asp)))
    # text block (for camera framing) per text page
    blocks = {}
    for r in ("left", "right"):
        if pages[r] and pages[r].get("ocr"):
            ls = [l for l in ocr_lines(res[text_roles.index(r)], 0.3) if text_len(l["t"]) >= 8]
            if ls:
                xs0 = sorted(l["x0"] for l in ls); xs1 = sorted(l["x1"] for l in ls)
                blocks[r] = [xs0[len(xs0) // 10], xs1[int(len(xs1) * 0.9) - 1 if len(xs1) > 1 else 0]]
    toc_hl = None
    if pages["toc"] and a.article_title:
        toc_hl = T.find_toc_entry(ocr_lines(res[text_roles.index("toc")], 0.0, merge=False), a.article_title)
    cfg = {
        "version": 1, "slug": a.slug, "root": root, "fps": 30,
        "title_text": a.title_text, "article_title": a.article_title,
        "pages": pages, "fillers": fillers, "endpaper": "textures/endpaper.png",
        "book": {"W": round(W, 4), "H": H}, "text_block": blocks, "toc_highlight": toc_hl,
        "voice": "白桦", "intro_seconds": 5.4, "outro_seconds": 1.3, "gap_comma": 0.30, "gap_full": 0.50,
        "highlight_color": [0.91, 0.33, 0.30], "cards": [], "props": [],
        "render": {"frames_dir": "render/frames", "samples": 32, "percent": 100},
    }
    save_project(root, cfg)
    print(f"project: {root}/project.json  book W={W:.4f} H={H}  toc_highlight={toc_hl}")
    for r in ("left", "right"):
        if pages[r] and pages[r].get("ocr"):
            print(f"--- OCR {r} page (y px | text) ---")
            for l in ocr_lines(res[text_roles.index(r)], 0.0):
                print(f"{int(l['y0']):5d} | {l['t']}")

if __name__ == "__main__":
    main()
