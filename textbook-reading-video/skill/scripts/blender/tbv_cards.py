# -*- coding: utf-8 -*-
# Optional floating paper-cut illustration cards (Z-stacked layers, parallax, follow the reading camera)
# and small 3D props (e.g. an orange popping out of the word 橘子). Driven by project.json "cards"/"props".
import bpy, bmesh, math

RIG_FOLLOW = 0.70
RIG_ABOVE = 0.0150          # card group centre sits this far above the camera aim (page y)
LAYER_Z = {1: 0.006, 2: 0.013, 3: 0.024}

def _kf(ob, path, pairs, index=-1, interp='BEZIER'):
    _keys(ob, path, sorted(pairs), interp, index)

def pop(ob, t0, t1, s=1.0, over=1.08):
    tm = t0 + (t1 - t0) * 0.72
    for ax in range(3):
        _kf(ob, "scale", [(t0, 0.001), (tm, s * over), (t1, s)], ax)

def unpop(ob, t0, t1, s=1.0):
    for ax in range(3):
        _kf(ob, "scale", [(t0, s), (t1, 0.001)], ax)

def _cam_aim_at(t):
    ks = CAM_KEYS
    for a, b in zip(ks, ks[1:]):
        if a[0] <= t <= b[0]:
            u = (t - a[0]) / max(1e-6, b[0] - a[0])
            return a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u
    return ks[-1][1], ks[-1][2]

def make_card(name, w, h, path, coll, parent, loc, thick_layers=2, tint=(1, 1, 1)):
    """alpha-cut card plane + darker copies underneath to fake paper thickness"""
    me = bpy.data.meshes.new(name)
    me.from_pydata([(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0)], [], [(0, 1, 2, 3)])
    uvl = me.uv_layers.new(name="UVMap")
    for li, uv in zip(range(4), [(0, 0), (1, 0), (1, 1), (0, 1)]):
        uvl.data[li].uv = uv
    me.materials.append(mat_card("TBV_M_" + name, path, tint=tint))
    ob = bpy.data.objects.new(name, me); coll.objects.link(ob)
    ob.parent = parent; ob.location = loc
    dark = mat_card("TBV_M_" + name + "_edge", path, tint=(0.62 * tint[0], 0.60 * tint[1], 0.57 * tint[2]))
    for k in range(thick_layers):
        me2 = me.copy(); me2.name = f"{name}_thk{k}"
        me2.materials[0] = dark
        o2 = bpy.data.objects.new(f"{name}_thk{k}", me2); coll.objects.link(o2)
        o2.parent = ob; o2.location = (0, 0, -0.00028 * (k + 1))
    ob["image"] = path or "placeholder"
    return ob

def make_ball(name, r, mat, coll, parent=None, loc=(0, 0, 0), stem=True):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=r)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me); coll.objects.link(ob)
    ob.parent = parent; ob.location = loc; ob.scale = (1.0, 1.0, 0.86)
    if stem:
        st = bpy.data.meshes.new(name + "_stem")
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=r * 0.16, radius2=r * 0.08, depth=r * 0.35)
        bm.to_mesh(st); bm.free()
        st.materials.append(mat_simple("TBV_M_stem", (0.10, 0.16, 0.05), rough=0.6))
        so = bpy.data.objects.new(name + "_stem", st); coll.objects.link(so)
        so.parent = ob; so.location = (0, 0, r * 1.02)
    return ob

def _t_in(i, lead=0.35):
    return max(T_READ0 - 0.2, sentence_times(i)[0] - lead)

def _t_out(i):
    return sentence_times(i)[1] + 0.15

def _card_size(c, path):
    w = float(c.get("w", 0.06))
    if c.get("h"):
        return w, float(c["h"])
    im = load_img(path, alpha=True) if path else None
    if im is not None and im.size[0] > 0:
        return w, w * im.size[1] / im.size[0]
    return w, w * 0.6

def _animate_card(ob, c, z, t_end_all):
    rot = math.radians(float(c.get("rot", 0.0)))
    ob.rotation_euler.z = rot
    ti = _t_in(int(c.get("from", TL[0]["i"])))
    enter = c.get("enter", "pop")
    if enter == "top":      # slides down into the frame
        pop(ob, ti, ti + 0.7, over=1.03)
        _kf(ob, "location", [(ti, ob.location.y + 0.030), (ti + 0.7, ob.location.y)], 1)
    else:                   # pops up out of the page
        pop(ob, ti, ti + 0.55, over=1.06)
        _kf(ob, "location", [(ti, z - 0.0045), (ti + 0.55, z)], 2)
        _kf(ob, "rotation_euler", [(ti, rot - math.radians(9)), (ti + 0.55, rot)], 2)
    t_out = None
    if c.get("to") is not None:
        t_out = _t_out(int(c["to"]))
        unpop(ob, t_out, t_out + 0.6)
        _kf(ob, "location", [(t_out, ob.location.y), (t_out + 0.6, ob.location.y + 0.04)], 1)
    rk = c.get("rot_keys") or []          # [[sentence, degrees], ...] e.g. lean while climbing
    if rk:
        pairs = [(ti + 0.6, rot)]
        for (si, deg) in rk:
            ts = sentence_times(int(si))[0]
            pairs += [(ts, pairs[-1][1]), (ts + 1.2, rot + math.radians(float(deg)))]
        _kf(ob, "rotation_euler", pairs, 2)
    return ti, t_out

def build_cards():
    cards = PROJ.get("cards") or []
    props = PROJ.get("props") or []
    if not cards and not props:
        return None
    coll = get_coll("TBV_Cards")
    rig = bpy.data.objects.new("TBV_CardRig", None); coll.objects.link(rig)
    rig.empty_display_type = 'CUBE'; rig.empty_display_size = 0.01
    C = {"rig": rig, "cards": [], "props": []}
    firsts = [int(c.get("from", TL[0]["i"])) for c in cards]
    t_ref = sentence_times(min(firsts))[0] if firsts else T_READ0
    ay0 = _target_at(t_ref + 0.1)[1]     # aim of the row being read when the first card appears
    kt = [k[0] for k in CAM_KEYS if T_READ0 - 0.2 <= k[0] <= T_READ1][::3]
    for ax in range(3):
        pairs = []
        for t in kt:
            _, ay = _cam_aim_at(t)
            p = (XC[READ_PAGE], ay0 + RIG_ABOVE + RIG_FOLLOW * (ay - ay0), ZP)
            pairs.append((t, p[ax]))
        _kf(rig, "location", pairs, ax)
    for k, c in enumerate(cards):
        path = ab(c.get("image"))
        w, h = _card_size(c, path)
        layer = int(c.get("layer", k % 3 + 1))
        z = float(c.get("z", LAYER_Z.get(layer, 0.013)))
        holder = rig
        if c.get("flip"):   # two-sided card: flips (rotation Y by pi) to the second image at sentence 'at'
            holder = bpy.data.objects.new(f"TBV_CardFlip_{k:02d}", None); coll.objects.link(holder)
            holder.parent = rig; holder.empty_display_size = 0.006
            holder.location = (float(c.get("x", 0.0)), float(c.get("y", 0.0)), z)
            loc = (0.0, 0.0, 0.0)
        else:
            loc = (float(c.get("x", 0.0)), float(c.get("y", 0.0)), z)
        ob = make_card(f"TBV_Card_{k:02d}", w, h, path, coll, holder, loc,
                       thick_layers=2 if layer < 3 else 1, tint=tuple(c.get("tint", (1, 1, 1))))
        anim_ob = holder if c.get("flip") else ob
        ti, t_out = _animate_card(anim_ob, c, z, T_READ1)
        objs = [ob] + list(ob.children)
        if c.get("flip"):
            fp = ab(c["flip"].get("image"))
            back = make_card(f"TBV_Card_{k:02d}b", w, h, fp, coll, holder, (0, 0, -0.0009),
                             thick_layers=1, tint=tuple(c.get("tint", (1, 1, 1))))
            back.rotation_euler = (0.0, math.pi, 0.0)
            ta = sentence_times(int(c["flip"]["at"]))[0]
            _kf(holder, "rotation_euler", [(ta - 0.2, 0.0), (ta + 0.6, math.pi)], 1)
            objs += [back] + list(back.children)
        for o in objs:
            _vis(o, ti - 0.02, (t_out + 0.62) if t_out else None)
        C["cards"].append(ob)
    for k, p in enumerate(props):
        _build_prop(k, p, coll, rig, C)
    return C

def _build_prop(k, p, coll, rig, C):
    """kind fruit|ball. Anchored on a page word ("word") or in the card rig ("attach": "rig")."""
    r = float(p.get("r", 0.0034))
    color = tuple(p.get("color", (0.807, 0.184, 0.027)))
    mat = mat_fruit(f"TBV_M_prop{k:02d}", color)
    stem = p.get("kind", "fruit") == "fruit"
    name = f"TBV_Prop_{k:02d}"
    if p.get("word"):
        hit = find_word(p["word"], p.get("sentence"))
        if hit is None:
            print(f"!! prop {k}: word {p['word']!r} not found in reading chars, skipped")
            return None
        i, page, lt, lh, x0, x1 = hit
        cx = 0.5 * (x0 + x1)
        wx, wy = page_xy(cx, lt + 0.5 * lh, page)
        z0 = page_z(wx, page) + 0.001
        ob = make_ball(name, r, mat, coll, None, (wx, wy + 0.0062, z0), stem=stem)
        ti = max(T_READ0, char_time(i, page, lt, cx) - 0.25)
        if p.get("until") is not None:
            t_end = _t_out(int(p["until"]))
        else:
            t_end = min(T_READ1, ti + 4.5)
        t_end = max(t_end, ti + 1.6)
        pop(ob, ti, ti + 0.43, over=1.12)
        zs = [(ti, z0), (ti + 0.43, z0 + 0.0075)]
        t = ti + 1.6; up = False
        while t < t_end - 0.9:
            zs.append((t, z0 + (0.0072 if up else 0.0062))); up = not up; t += 1.2
        zs.append((t_end, z0 + 0.030))
        _kf(ob, "location", zs, 2)
        unpop(ob, t_end - 0.7, t_end)
        objs = [ob] + list(ob.children)
        for o in objs:
            _vis(o, ti - 0.02, t_end + 0.02)
    else:
        loc = (float(p.get("x", 0.0)), float(p.get("y", 0.0)), float(p.get("z", 0.02)))
        ob = make_ball(name, r, mat, coll, rig, loc, stem=stem)
        ti = _t_in(int(p.get("from", TL[0]["i"])), lead=-0.05) + float(p.get("delay", 0.0))
        pop(ob, ti, ti + 0.42, over=1.16)
        t_out = _t_out(int(p["to"])) if p.get("to") is not None else None
        if t_out:
            unpop(ob, t_out, t_out + 0.5)
        for o in [ob] + list(ob.children):
            _vis(o, ti - 0.02, (t_out + 0.52) if t_out else None)
    C["props"].append(ob)
    return ob
