# -*- coding: utf-8 -*-
# Numeric QA of the built scene: camera footprint, highlight/card screen positions per sentence.
import bpy, json, os
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

def footprint(z_plane=None):
    scn = bpy.context.scene
    cam = scn.camera
    z_plane = ZP if z_plane is None else z_plane
    mw = cam.matrix_world
    origin = mw.translation
    out = []
    for v in cam.data.view_frame(scene=scn):   # TR, BR, BL, TL in camera space
        d = (mw.to_3x3() @ v).normalized()
        if abs(d.z) < 1e-9:
            out.append(None); continue
        k = (z_plane - origin.z) / d.z
        p = origin + d * k
        out.append((round(p.x, 4), round(p.y, 4)))
    return out

def screen_bbox(ob):
    """bbox of the evaluated geometry in screen space: (x0, y0, x1, y1) in 0..1, y from the top"""
    scn = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    oe = ob.evaluated_get(dg)
    pts = [oe.matrix_world @ Vector(c) for c in oe.bound_box]
    xs, ys = [], []
    for p in pts:
        q = world_to_camera_view(scn, scn.camera, p)
        xs.append(q.x); ys.append(1.0 - q.y)
    return [round(min(xs), 3), round(min(ys), 3), round(max(xs), 3), round(max(ys), 3)]

def _visible(o):
    while o is not None:
        if o.hide_render:
            return False
        o = o.parent
    return True

CAPTION_TOP = 0.80      # captions + bottom fade start around y = 0.71..0.80 of the frame

def report(path=None):
    """checks at the middle of every sentence: the growing band is inside the frame and above the captions"""
    scn = bpy.context.scene
    bands = {o.name: o for o in bpy.data.objects if o.name.startswith("TBV_HL_")}
    cards = [o for o in bpy.data.objects if (o.name.startswith("TBV_Card_") and "thk" not in o.name)
             or o.name.startswith("TBV_Prop_")]
    res = {"sentences": [], "warnings": [], "toc": None}
    for (i, j, g, t0, t1, t_off) in SCHED:
        t = 0.5 * (t0 + t1)
        scn.frame_set(int(round(fr(t))))
        b = bands.get(f"TBV_HL_S{i:02d}_{j}")
        if b is None:
            continue
        bb = screen_bbox(b)
        ent = {"i": i, "seg": j, "t": round(t, 2), "band": bb, "cards": []}
        if bb[0] < 0.0 or bb[2] > 1.0 or bb[1] < 0.06 or bb[3] > CAPTION_TOP:
            res["warnings"].append(f"sentence {i} seg {j}: band {bb} outside the safe area")
        for o in cards:
            if _visible(o) and o.matrix_world.to_scale().x > 0.3:
                cb = screen_bbox(o)
                ent["cards"].append([o.name, cb])
                ov = not (cb[2] < bb[0] or cb[0] > bb[2] or cb[3] < bb[1] or cb[1] > bb[3])
                if ov:
                    res["warnings"].append(f"sentence {i}: card {o.name} {cb} covers the read line {bb}")
        res["sentences"].append(ent)
    if "TBV_HL_TOC" in bands:
        scn.frame_set(int(round(fr(3.0))))
        res["toc"] = screen_bbox(bands["TBV_HL_TOC"])
    for t in (0.0, 2.0, 4.4, T_READ0, DURATION - 0.05):
        scn.frame_set(int(round(fr(t))))
        res.setdefault("footprints", []).append([round(t, 2), footprint()])
    scn.frame_set(1)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    return res
