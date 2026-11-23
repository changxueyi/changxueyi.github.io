# -*- coding: utf-8 -*-
# Marker highlight bands synced to the narration (+ TOC band). Bands are plain mesh strips 2 mm above
# the paper, origin at the left end, so they can be selected and nudged along X/Y in the viewport.
import bpy, math

HL_COLOR = tuple(PROJ.get("highlight_color") or (0.91, 0.33, 0.30))   # transmittance -> multiply

def _keys(ob, path, pairs, interp='LINEAR', index=-1):
    prefs = bpy.context.preferences.edit
    old = prefs.keyframe_new_interpolation_type
    prefs.keyframe_new_interpolation_type = interp
    try:
        for t, val in pairs:
            if index >= 0:
                getattr(ob, path)[index] = val
            else:
                setattr(ob, path, val)
            ob.keyframe_insert(path, index=index, frame=fr(t))
    finally:
        prefs.keyframe_new_interpolation_type = old

def _vis(ob, t_on, t_off):
    """hide_render outside [t_on, t_off] (constant keys)"""
    ob.hide_render = True; ob.keyframe_insert("hide_render", frame=1)
    ob.hide_render = False; ob.keyframe_insert("hide_render", frame=max(1, int(math.floor(fr(t_on)))))
    if t_off is not None:
        ob.hide_render = True; ob.keyframe_insert("hide_render", frame=int(math.ceil(fr(t_off))))

def make_band(name, x0, x1, y0, y1, zfun, mat, coll):
    """flat strip following the paper surface, origin at its left end (grows by scale X)"""
    L = x1 - x0
    n = max(2, int(abs(L) / 0.002))
    yc = 0.5 * (y0 + y1)
    z0 = zfun(x0) + HL_LIFT
    verts, faces = [], []
    for i in range(n + 1):
        x = x0 + L * i / n
        z = zfun(x) + HL_LIFT
        verts += [(x - x0, y0 - yc, z - z0), (x - x0, y1 - yc, z - z0)]
    for i in range(n):
        a = 2 * i
        faces.append((a, a + 2, a + 3, a + 1))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob.location = (x0, yc, z0)
    ob.visible_shadow = False
    return ob

def band_anim(ob, t0, t1, t_off):
    _keys(ob, "scale", [(t0 - 0.02, 0.0001), (t0, 0.0001), (t1, 1.0)], 'LINEAR', 0)
    _keys(ob, "scale", [(t_off, 1.0), (t_off + 0.2, 0.0001)], 'LINEAR', 1)
    _vis(ob, t0 - 0.05, t_off + 0.25)

def build_bands():
    coll = get_coll("TBV_Highlights")
    mat = mat_highlight("TBV_M_highlight", HL_COLOR)
    made = []
    for (i, j, g, t0, t1, t_off) in SCHED:
        role = g.get("page", "right")
        x0, _ = page_xy(g["x0"], 0, role)
        x1, _ = page_xy(g["x1"], 0, role)
        _, ya = page_xy(0, g["line_top"] + BAND_TOP * g["line_h"], role)
        _, yb = page_xy(0, g["line_top"] + BAND_BOT * g["line_h"], role)
        ob = make_band(f"TBV_HL_S{i:02d}_{j}", x0, x1, yb, ya, (lambda x, r=role: page_z(x, r)), mat, coll)
        band_anim(ob, t0, t1, t_off)
        ob["sentence"] = READING[i]["text"]
        ob["page_px"] = [g["x0"], g["x1"], g["line_top"], g["line_h"]]
        made.append(ob)
    th = PROJ.get("toc_highlight")
    if HAS_TOC and th:   # the article's TOC entry on P2 (resting on the right until 3.30 s)
        x0, _ = page_xy(th["x0"], 0, "toc"); x1, _ = page_xy(th["x1"], 0, "toc")
        _, ya = page_xy(0, th["line_top"] + 0.40 * th["line_h"], "toc")
        _, yb = page_xy(0, th["line_top"] + 1.00 * th["line_h"], "toc")
        toc = make_band("TBV_HL_TOC", x0, x1, yb, ya, toc_z, mat, coll)
        band_anim(toc, 2.55, 3.05, 3.08)
        made.append(toc)
    return made
