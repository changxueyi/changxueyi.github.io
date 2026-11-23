#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Align the passage to read (片段文案) with the page OCR -> project['reading'] (caption/TTS sentences + band boxes).

  align.py --project DIR --text "我说道：“爸爸，你走吧。”他往车外看了看说：……"   # one paragraph -> auto-split
  align.py --project DIR --text-file passage.txt     # several lines -> one caption sentence per line
  align.py --project DIR                             # no text: prints the page OCR and exits 2
Options: --page auto|right|left (auto tries right, left and left+right; right wins ties),
         --split auto|lines|para, --max-clause 16, --pad 0 (px added to band ends), --dry-run, --force.
Exit codes: 0 ok, 1 match ratio < 0.5 (not saved unless --force), 2 no text given.
"""
import argparse, difflib, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tbv_common import load_project, save_project, ocr_lines, text_len, ANNOT, PUNCT, FINAL, CLOSE, OPEN

BREAK = set("，。！？；：…")
PAUSE = set("，、；：")
STRIP = PUNCT | ANNOT | set("〔〕[]【】<>-_/|·•")

def spoken(ch):
    """characters that take part in the alignment (everything that is read aloud)"""
    return not (ch in STRIP or ch.isspace())

def clean_text(s):
    """user text -> caption/TTS text: drop annotation marks, CJK spaces; ASCII punctuation -> full width"""
    s = "".join(ch for ch in s if ch not in ANNOT)
    s = re.sub(r"\s+(?=[^\x00-\x7f])|(?<=[^\x00-\x7f])\s+", "", s.strip())
    s = re.sub(r"\s+", " ", s).replace("...", "……")
    tbl = {",": "，", ";": "；", ":": "：", "?": "？", "!": "！", "(": "（", ")": "）"}
    s = "".join(tbl.get(ch, ch) for ch in s)
    s = re.sub(r"(?<=[\u4e00-\u9fff])\.", "。", s)
    out, k = [], 0
    for ch in s:                                   # straight double quotes -> “ ”
        if ch == '"':
            out.append("“" if k % 2 == 0 else "”"); k += 1
        else:
            out.append(ch)
    return "".join(out)

def atomic_clauses(s):
    """cut after break punctuation; closing quotes/brackets stay with the clause before"""
    out, cur, i, n = [], "", 0, len(s)
    while i < n:
        ch = s[i]; cur += ch; i += 1
        if ch in BREAK:
            while i < n and (s[i] in BREAK or s[i] in CLOSE):
                cur += s[i]; i += 1
            out.append(cur); cur = ""
    if cur:
        if out and text_len(cur) == 0:
            out[-1] += cur
        else:
            out.append(cur)
    return out

def _depths(clauses):
    """quote depth before / after every clause"""
    d, res = 0, []
    for c in clauses:
        b = d
        for ch in c:
            if ch in "“‘「『":
                d += 1
            elif ch in "”’」』":
                d = max(0, d - 1)
        res.append((b, d))
    return res

def _ends_final(c):
    t = c.rstrip("".join(CLOSE))
    return bool(t) and t[-1] in FINAL

def split_passage(s, max_clause=16, min_clause=4):
    """narration: one unit per comma clause; a quoted sentence is one unit; a short lead-in
    (……说：) joins a complete short quote; tiny pieces join a neighbour"""
    cl = atomic_clauses(s)
    dep = _depths(cl)
    units = []                                     # [text, depth_before, depth_after]
    for c, (b, a) in zip(cl, dep):
        if units:
            u = units[-1]
            inside = u[2] > 0 and b > 0            # previous clause left a quote open
            if inside and not _ends_final(u[0]) and text_len(u[0] + c) <= max_clause:
                u[0] += c; u[2] = a
                continue
        units.append([c, b, a])
    out = []
    for u in units:                                # lead-in + complete short quote
        if out:
            p = out[-1]
            lead = p[1] == 0 and p[0].rstrip().endswith("：") and p[2] == 0
            whole = u[1] == 0 and u[0][:1] in OPEN and u[2] == 0
            if lead and whole and text_len(p[0] + u[0]) <= max_clause:
                p[0] += u[0]; p[2] = u[2]
                continue
        out.append(list(u))
    texts = [u[0] for u in out]
    k = 0
    while k < len(texts):                          # tiny pieces
        t = texts[k]
        if text_len(t) < min_clause and len(texts) > 1:
            nxt = k + 1 < len(texts) and not _ends_final(t) and text_len(t + texts[k + 1]) <= max_clause + 4
            if nxt:
                texts[k:k + 2] = [t + texts[k + 1]]
                continue
            if k > 0 and text_len(texts[k - 1] + t) <= max_clause + 4:
                texts[k - 1:k + 1] = [texts[k - 1] + t]
                k -= 1
                continue
        k += 1
    return texts

def sentences_from_text(raw, mode="auto", max_clause=16):
    lines = [l.strip() for l in raw.replace("\r", "\n").split("\n") if l.strip()]
    if mode == "auto":
        wrapped = any(text_len(l) >= 12 and l[-1] not in PUNCT and l[-1] not in CLOSE for l in lines[:-1])
        mode = "lines" if len(lines) > 1 and not wrapped else "para"
    if mode == "lines":
        sents = [clean_text(l) for l in lines]
    else:
        sents = split_passage(clean_text("".join(lines)), max_clause)
    return [s for s in sents if text_len(s) > 0], mode

# ---------------------------------------------------------------- OCR stream + alignment
def page_stream(cfg, root, page):
    """OCR chars of one page in reading order: dicts {c, page, row, x0, x1, top, lh}; None if no OCR"""
    p = (cfg.get("pages") or {}).get(page)
    if not p or not p.get("ocr"):
        return None
    with open(os.path.join(root, p["ocr"]), encoding="utf-8") as f:
        rows = ocr_lines(json.load(f), 0.0)
    hs = sorted(r["h"] for r in rows if text_len(r["t"]) >= 8) or sorted(r["h"] for r in rows)
    lh = hs[len(hs) // 2] if hs else 24.0          # one band height per page (median body row)
    out = []
    for ri, r in enumerate(rows):
        top = (r["y0"] + r["y1"]) / 2 - lh / 2
        for ch, a, b in r["chars"]:
            out.append({"c": ch, "page": page, "row": ri, "x0": a, "x1": b, "top": top, "lh": lh})
    return out

def _filter_blocks(blocks, unit_starts, min_anchor):
    """drop spurious matches: small blocks off the diagonal of their anchors, and anchors that
    imply a jump in the page text where the passage has no clause boundary"""
    anchors = [m for m in blocks if m.size >= min_anchor] or [m for m in blocks if m.size >= 2] or list(blocks)
    keep = []
    for m in blocks:
        if m in anchors:
            keep.append(m); continue
        prev = [x for x in anchors if x.a + x.size <= m.a]
        nxt = [x for x in anchors if x.a >= m.a + m.size]
        d = m.b - m.a
        if (prev and abs(d - (prev[-1].b - prev[-1].a)) <= 2) or (nxt and abs(d - (nxt[0].b - nxt[0].a)) <= 2):
            keep.append(m)
    bset = set(unit_starts)
    changed = True
    while changed and len(keep) > 1:
        changed = False
        for k in range(len(keep) - 1):
            p, n = keep[k], keep[k + 1]
            pa, pb, ag, bg = p.a + p.size, p.b + p.size, n.a - (p.a + p.size), n.b - (p.b + p.size)
            if bg - ag > 10 and not any(pa <= s <= n.a for s in bset):
                small = p if p.size <= n.size else n
                if small.size < 6:
                    keep.remove(small); changed = True
                    break
    return keep

def align(pchars, stream, unit_starts, min_anchor=3):
    """map every normalised passage char to a stream index.
    returns omap (index or None) and exact flags"""
    oidx = [k for k, e in enumerate(stream) if spoken(e["c"])]
    A = "".join(pchars)
    B = "".join(stream[k]["c"] for k in oidx)
    sm = difflib.SequenceMatcher(None, A, B, autojunk=False)
    blocks = [m for m in sm.get_matching_blocks() if m.size]
    kb = _filter_blocks(blocks, unit_starts, min_anchor)
    omap, exact = [None] * len(A), [False] * len(A)
    for m in kb:
        for k in range(m.size):
            omap[m.a + k] = m.b + k; exact[m.a + k] = True
    for gi in range(len(kb) + 1):
        pa = kb[gi - 1].a + kb[gi - 1].size if gi > 0 else 0
        pb = kb[gi - 1].b + kb[gi - 1].size if gi > 0 else None
        na = kb[gi].a if gi < len(kb) else len(A)
        nb = kb[gi].b if gi < len(kb) else None
        ag = na - pa
        if ag <= 0 or (pb is None and nb is None):
            continue
        if pb is not None and nb is not None and nb - pb == ag:
            for k in range(ag):
                omap[pa + k] = pb + k             # same length: OCR misread these chars
            continue
        inner = [s for s in unit_starts if pa < s < na]
        if pb is None:
            cut = pa
        elif nb is None:
            cut = na
        elif inner:
            cut = min(inner, key=lambda s: abs(s - (pa + na) / 2))
        else:
            cut = pa + ag // 2
        for k in range(pa, cut):                  # continue the diagonal of the block before
            o = pb + (k - pa)
            if o < len(B) and (nb is None or o < nb):
                omap[k] = o
        for k in range(cut, na):                  # ... and of the block after
            o = nb - (na - k)
            if o >= 0 and (pb is None or o >= pb):
                omap[k] = o
    return [oidx[o] if o is not None else None for o in omap], exact

# ---------------------------------------------------------------- reading entries
def _lead_trail(t):
    lead = 0
    for ch in t:
        if ch in PUNCT:
            lead += 1
        else:
            break
    trail = 0
    for ch in reversed(t):
        if ch in PUNCT:
            trail += 1
        else:
            break
    return lead, trail

def build_reading(sents, stream, omap, exact, pad=0.0):
    reading, j = [], 0
    for i, t in enumerate(sents, 1):
        n = sum(1 for ch in t if spoken(ch))
        js = list(range(j, j + n)); j += n
        hits = sum(exact[k] for k in js)
        # a sentence without a single exact match is not on the page (extrapolated positions are guesses)
        mapped = [omap[k] for k in js if omap[k] is not None] if hits else []
        mset = set(mapped)
        ent = {"i": i, "text": t, "segments": [], "chars": [],
               "ratio": round(hits / max(1, n), 3)}
        if mapped:
            st, en = min(mapped), max(mapped)
            lead, trail = _lead_trail(t)
            while lead and st > 0 and stream[st - 1]["row"] == stream[st]["row"] and stream[st - 1]["page"] == stream[st]["page"] \
                    and not spoken(stream[st - 1]["c"]):
                st -= 1; lead -= stream[st]["c"] in PUNCT
            while en + 1 < len(stream) and stream[en + 1]["row"] == stream[en]["row"] and stream[en + 1]["page"] == stream[en]["page"] \
                    and not spoken(stream[en + 1]["c"]) and (trail or stream[en + 1]["c"] in ANNOT):
                en += 1; trail -= stream[en]["c"] in PUNCT and trail > 0
            tail = set(range(en - _lead_trail(t)[1] + 1, en + 1))
            groups = []
            for k in range(st, en + 1):
                e = stream[k]
                if not groups or (groups[-1][0]["page"], groups[-1][0]["row"]) != (e["page"], e["row"]):
                    groups.append([])
                groups[-1].append(dict(e, k=k))
            for g in groups:
                if not any(e["k"] in mset for e in g):
                    continue                      # footnotes / page break / skipped text inside the span
                w = sum(1.0 if spoken(e["c"]) else (0.5 if e["c"] in PAUSE and e["k"] not in tail else 0.0) for e in g)
                ent["segments"].append({"page": g[0]["page"], "line_top": round(g[0]["top"], 1), "line_h": round(g[0]["lh"], 1),
                                        "x0": round(min(e["x0"] for e in g) - pad, 1), "x1": round(max(e["x1"] for e in g) + pad, 1),
                                        "weight": max(0.5, w)})
        last = None
        spk = [c for c in t if spoken(c)]
        for idx, k in enumerate(js):              # spoken chars of `text` with their boxes
            ch = spk[idx]
            if not hits:
                break
            if omap[k] is not None:
                e = stream[omap[k]]; last = e
                ent["chars"].append({"c": ch, "page": e["page"], "line_top": round(e["top"], 1), "line_h": round(e["lh"], 1),
                                     "x0": round(e["x0"], 1), "x1": round(e["x1"], 1), "exact": bool(exact[k])})
            else:
                nxt = next((stream[omap[q]] for q in js[idx + 1:] if omap[q] is not None), None)
                e = last or nxt
                if e is None:
                    continue
                x = e["x1"] if e is last else e["x0"]
                ent["chars"].append({"c": ch, "page": e["page"], "line_top": round(e["top"], 1), "line_h": round(e["lh"], 1),
                                     "x0": round(x, 1), "x1": round(x, 1), "exact": False})
        reading.append(ent)
    return reading

def unit_starts_of(sents):
    out, j = [], 0
    for t in sents:
        out.append(j); j += sum(1 for ch in t if spoken(ch))
    return out

def try_pages(cfg, root, sents, which):
    pchars = [ch for t in sents for ch in t if spoken(ch)]
    us = unit_starts_of(sents)
    streams = {p: page_stream(cfg, root, p) for p in ("left", "right")}
    cands = []
    order = ["right", "left", "both"] if which == "auto" else [which]
    for name in order:
        if name == "both":
            if not (streams["left"] and streams["right"]):
                continue
            st = streams["left"] + streams["right"]
        else:
            st = streams.get(name)
            if not st:
                continue
        omap, exact = align(pchars, st, us)
        cands.append((sum(exact) / max(1, len(pchars)), name, st, omap, exact))
    if not cands:
        sys.exit("no OCR for the requested page(s); run init_project.py first")
    best = cands[0]
    for c in cands[1:]:
        if c[0] > best[0] + 0.01:
            best = c
    return best, [(round(c[0], 3), c[1]) for c in cands]

# ---------------------------------------------------------------- CLI
def print_ocr(cfg, root):
    for page in ("left", "right"):
        p = (cfg.get("pages") or {}).get(page)
        if not p or not p.get("ocr"):
            continue
        with open(os.path.join(root, p["ocr"]), encoding="utf-8") as f:
            rows = ocr_lines(json.load(f), 0.0)
        print(f"--- OCR {page} page (y px | text) ---")
        for r in rows:
            print(f"{int(r['y0']):5d} | {r['t']}")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--text")
    g.add_argument("--text-file")
    ap.add_argument("--page", choices=("auto", "right", "left"), default="auto")
    ap.add_argument("--split", choices=("auto", "lines", "para"), default="auto")
    ap.add_argument("--max-clause", type=int, default=16)
    ap.add_argument("--pad", type=float, default=0.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.project)
    cfg = load_project(root)
    raw = a.text
    if a.text_file:
        with open(a.text_file, encoding="utf-8") as f:
            raw = f.read()
    if not raw or not raw.strip():
        print_ocr(cfg, root)
        sys.stdout.flush()
        print("\nno passage given: pick a contiguous passage (about 100-170 characters, from one page) in the OCR "
              "above and rerun with --text or --text-file", file=sys.stderr)
        sys.exit(2)
    sents, mode = sentences_from_text(raw, a.split, a.max_clause)
    if not sents:
        sys.exit("the passage has no readable characters")
    (ratio, page, stream, omap, exact), scores = try_pages(cfg, root, sents, a.page)
    reading = build_reading(sents, stream, omap, exact, a.pad)
    print(f"split={mode}  page={page}  ratio={ratio:.3f}  candidates={scores}")
    print(" i | rows | ratio | text")
    for r in reading:
        rows = ",".join(f"{s['page'][0].upper()}{s['line_top']:.0f}" for s in r["segments"]) or "-"
        print(f"{r['i']:2d} | {rows} | {r['ratio']:.2f} | {r['text']}")
    warn = []
    long_ = [r["i"] for r in reading if text_len(r["text"]) > 18]
    if long_:
        warn.append(f"sentences {long_} are longer than 18 characters (the caption font shrinks); consider splitting")
    lost = [r["i"] for r in reading if not r["segments"]]
    if lost:
        warn.append(f"sentences {lost} were not found on the page: no highlight band for them")
    weak = [r["i"] for r in reading if r["segments"] and r["ratio"] < 0.6]
    if weak:
        warn.append(f"sentences {weak} matched poorly (< 0.6); compare them with the page")
    if ratio < 0.8:
        warn.append(f"overall match ratio {ratio:.2f} < 0.8: wrong page, OCR trouble or text differs from the print")
    for w in warn:
        print("WARNING: " + w, file=sys.stderr)
    if ratio < 0.5 and not a.force:
        print("ERROR: match ratio < 0.5, project.json not changed (use --force to keep it)", file=sys.stderr)
        sys.exit(1)
    if a.dry_run:
        return
    cfg = load_project(root)                      # reload: keep keys other stages wrote meanwhile
    old = [t.get("text") for t in cfg.get("timeline") or []]
    cfg["reading"] = reading
    cfg["align"] = {"page": page, "ratio": round(ratio, 3), "split": mode, "max_clause": a.max_clause,
                    "passage": "".join(sents)}
    save_project(root, cfg)
    print(f"saved {len(reading)} sentences -> {root}/project.json")
    if old and old != [r["text"] for r in reading]:
        print("NOTE: the existing narration timeline is for different text; rerun narrate.py", file=sys.stderr)

if __name__ == "__main__":
    main()
