# -*- coding: utf-8 -*-
# Book geometry: boards, page blocks, pages (exec'd after tbv_cfg + tbv_materials)
import bpy, bmesh, math
from mathutils import Vector

def _obj(name, me, coll):
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob

def make_box(name, x0, x1, y0, y1, z0, z1, mats, coll):
    """box with top(0)/bottom(1)/side(2) material slots, UV 0..1 on top & bottom"""
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    v = {}
    for ix, x in enumerate((x0, x1)):
        for iy, y in enumerate((y0, y1)):
            for iz, z in enumerate((z0, z1)):
                v[(ix, iy, iz)] = bm.verts.new((x, y, z))
    spec = [([(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], 0),
            ([(0, 1, 0), (1, 1, 0), (1, 0, 0), (0, 0, 0)], 1),
            ([(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)], 2),
            ([(1, 1, 0), (0, 1, 0), (0, 1, 1), (1, 1, 1)], 2),
            ([(0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1)], 2),
            ([(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)], 2)]
    for keys, mi in spec:
        f = bm.faces.new([v[k] for k in keys])
        f.material_index = mi
        for l in f.loops:
            co = l.vert.co
            l[uv].uv = ((co.x - x0) / (x1 - x0), (co.y - y0) / (y1 - y0)) if mi < 2 else (0.5, 0.5)
    me = bpy.data.meshes.new(name)
    bm.normal_update(); bm.to_mesh(me); bm.free()
    for m in mats:
        me.materials.append(m)
    return _obj(name, me, coll)

def make_block(name, side, mats, coll, flat_basis):
    """page stack; local z=0 at board top. Basis flat (closed book) or gutter profile."""
    bm = bmesh.new()
    tf, tb, bf, bb = [], [], [], []
    for i in range(NX + 1):
        s = W * i / NX
        z = H_REF if flat_basis else H_REF * G(s)
        x = side * s
        tf.append(bm.verts.new((x, -H / 2, z))); tb.append(bm.verts.new((x, H / 2, z)))
        bf.append(bm.verts.new((x, -H / 2, 0.0))); bb.append(bm.verts.new((x, H / 2, 0.0)))
    faces = []
    for i in range(NX):
        faces.append(((tf[i], tf[i + 1], tb[i + 1], tb[i]), 0))
        faces.append(((bf[i], bf[i + 1], tf[i + 1], tf[i]), 1))
        faces.append(((bb[i + 1], bb[i], tb[i], tb[i + 1]), 1))
    faces.append(((bf[-1], bb[-1], tb[-1], tf[-1]), 1))
    faces.append(((bb[0], bf[0], tf[0], tb[0]), 1))
    for vs, mi in faces:
        if side < 0:
            vs = tuple(reversed(vs))
        try:
            f = bm.faces.new(vs); f.material_index = mi
        except ValueError:
            pass
    me = bpy.data.meshes.new(name)
    bm.normal_update(); bm.to_mesh(me); bm.free()
    for m in mats:
        me.materials.append(m)
    ob = _obj(name, me, coll)
    ob.location = (0, 0, BT)
    if flat_basis:
        ob.shape_key_add(name="Basis")
        k = ob.shape_key_add(name="gutter", from_mix=False)
        for i, vtx in enumerate(me.vertices):
            co = vtx.co
            if co.z > 1e-7:
                k.data[i].co = (co.x, co.y, H_REF * G(abs(co.x)))
    return ob

def make_page_mesh(name):
    """grid in local XZ plane, normal +Y; x = distance from spine, z = -(page height coord)"""
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    g = {}
    for i in range(NX + 1):
        s = W * i / NX
        for j in range(NZ + 1):
            yp = -H / 2 + H * j / NZ
            g[(i, j)] = bm.verts.new((s, 0.0, -yp))
    for i in range(NX):
        for j in range(NZ):
            f = bm.faces.new((g[(i, j)], g[(i + 1, j)], g[(i + 1, j + 1)], g[(i, j + 1)]))
            for l in f.loops:
                co = l.vert.co
                l[uv].uv = (co.x / W, (-co.z + H / 2) / H)
    bm.normal_update()
    n = Vector()
    for f in bm.faces:
        n += f.normal
    if n.y < 0:
        for f in bm.faces:
            f.normal_flip()
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    return me

def add_page_keys(ob):
    ob.shape_key_add(name="Basis")
    for kname, fn in (("flatR", lambda s: H_REF), ("restR", lambda s: H_REF * G(s)),
                      ("restL", lambda s: -H_REF * G(s))):
        k = ob.shape_key_add(name=kname, from_mix=False)
        for i, vtx in enumerate(ob.data.vertices):
            co = vtx.co
            k.data[i].co = (co.x, fn(co.x), co.z)
        k.slider_min, k.slider_max = 0.0, 2.0

def make_page(name, front_path, back_path, edge_mat, coll, hinge_parent=None):
    me = make_page_mesh(name)
    me.materials.append(mat_paper(name + "_front", front_path))
    me.materials.append(mat_paper(name + "_back", back_path, mirror=True))
    me.materials.append(edge_mat)
    ob = _obj(name, me, coll)
    add_page_keys(ob)
    bend = ob.modifiers.new("Bend", 'SIMPLE_DEFORM')
    bend.deform_method = 'BEND'; bend.deform_axis = 'Z'; bend.angle = 0.0
    sol = ob.modifiers.new("Paper", 'SOLIDIFY')
    sol.thickness = PAGE_T; sol.offset = -1.0; sol.use_rim = True
    sol.material_offset = 1; sol.material_offset_rim = 2; sol.use_even_offset = True
    ob.rotation_euler = (math.pi / 2, 0.0, 0.0)
    if hinge_parent is not None:
        ob.parent = hinge_parent
    return ob

def set_rest(ob, flatR, restR, restL, frame=None):
    kbs = ob.data.shape_keys.key_blocks
    for kname, val in (("flatR", flatR), ("restR", restR), ("restL", restL)):
        kbs[kname].value = val
        if frame is not None:
            kbs[kname].keyframe_insert("value", frame=frame)

# ---------------- assemble the book + bake the intro (cover opening, page turns, riffle) ----------------
BOOK = {}

def _empty(name, loc, coll, size=0.02):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = 'ARROWS'; e.empty_display_size = size
    e.location = loc
    coll.objects.link(e)
    return e

def build_book():
    coll = get_coll("TBV_Book")
    paper_plain = mat_paper("TBV_M_paper_plain", None)
    edge_paper = mat_simple("TBV_M_paper_edge", (0.90, 0.885, 0.85), rough=0.85, spec=0.15)
    edges = mat_edges("TBV_M_block_edges")
    cloth = mat_cloth_board("TBV_M_cloth", cover_edge_colour(tex("cover")))
    endpaper = mat_paper("TBV_M_endpaper", ENDPAPER, tint=(0.94, 0.90, 0.82), rough=0.85)
    cover = mat_paper("TBV_M_cover", tex("cover"), tint=(1.0, 1.0, 1.0), rough=0.45)
    # back board (static, right side) + spine strip (closed state only)
    BOOK["back_board"] = make_box("TBV_BackBoard", 0.0, W + OV, -(H / 2 + OV), H / 2 + OV, 0.0, BT,
                                  [endpaper, cloth, cloth], coll)
    BOOK["spine"] = make_box("TBV_Spine", -0.0028, 0.0, -(H / 2 + OV), H / 2 + OV, 0.0, 2 * BT + T0,
                             [cloth, cloth, cloth], coll)
    # front cover board on its hinge
    ch = _empty("TBV_CoverHinge", (0.0, 0.0, BT + T0), coll)
    cb = make_box("TBV_CoverBoard", 0.0, W + OV, -(H / 2 + OV), H / 2 + OV, 0.0, BT,
                  [cover, endpaper, cloth], coll)
    cb.parent = ch
    BOOK["cover_hinge"], BOOK["cover_board"] = ch, cb
    # page blocks
    BOOK["rblock"] = make_block("TBV_BlockR", +1, [paper_plain, edges], coll, flat_basis=True)
    BOOK["lblock"] = make_block("TBV_BlockL", -1, [paper_plain, edges], coll, flat_basis=False)
    # static base page on the right = the right reading page
    base = make_page("TBV_Page_Base", tex("right"), None, edge_paper, coll)
    base.location = (0.0, 0.0, BT + BASE_EPS)
    BOOK["base"] = base
    # turning pages, each on its own hinge at the binding; the last one (PL) carries the left page
    BOOK["pages"] = []
    for (name, t0, dur, front, back, eR, eL) in TURNS:
        hg = _empty("TBV_Hinge_" + name, (0.0, 0.0, BT), coll, 0.01)
        pg = make_page("TBV_Page_" + name, front, back, edge_paper, coll, hinge_parent=hg)
        pg.location = (0.0, 0.0, eR)
        BOOK["pages"].append((pg, hg))
    return BOOK

def _key(ob, path, frame, index=-1):
    ob.keyframe_insert(path, index=index, frame=frame)

def bake_intro(t_end=5.2):
    """per-frame LINEAR keys for the whole intro (exact, no interpolation surprises)"""
    prefs = bpy.context.preferences.edit
    old = prefs.keyframe_new_interpolation_type
    prefs.keyframe_new_interpolation_type = 'LINEAR'
    try:
        ch, rb, lb, base = BOOK["cover_hinge"], BOOK["rblock"], BOOK["lblock"], BOOK["base"]
        f_end = int(round(fr(t_end)))
        for f in range(1, f_end + 1):
            t = (f - 1) / FPS
            g, hr, hl = gutter(t), hR(t), hL(t)
            phi, zh = cover_state(t)
            ch.location.z = zh; ch.rotation_euler.y = -phi
            _key(ch, "location", f, 2); _key(ch, "rotation_euler", f, 1)
            rb.scale.z = hr / H_REF; _key(rb, "scale", f, 2)
            kb = rb.data.shape_keys.key_blocks["gutter"]; kb.value = g
            kb.keyframe_insert("value", frame=f)
            lb.scale.z = max(hl, 1e-5) / H_REF; _key(lb, "scale", f, 2)
            set_rest(base, (1 - g) * hr / H_REF, g * hr / H_REF, 0.0, frame=f)
            for (name, t0, dur, front, back, eR, eL), (pg, hg) in zip(TURNS, BOOK["pages"]):
                th_r, th_e, u = turn_state(t, t0, dur)
                wR = 1.0 - smooth(u / 0.35)
                wL = smooth((u - 0.7) / 0.3)
                hg.rotation_euler.y = -th_r; _key(hg, "rotation_euler", f, 1)
                pg.modifiers["Bend"].angle = th_e - th_r
                pg.keyframe_insert('modifiers["Bend"].angle', frame=f)
                set_rest(pg, (1 - g) * hr / H_REF * wR, g * hr / H_REF * wR, hl / H_REF * wL, frame=f)
                sm = smooth(u)
                pg.location.z = eR * (1 - sm) - eL * sm; _key(pg, "location", f, 2)
        # visibility switches (constant keys on hide_render only)
        for ob, t_hide, start_hidden in ((BOOK["spine"], 1.20, False), (lb, 1.80, True)):
            ob.hide_render = start_hidden
            ob.keyframe_insert("hide_render", frame=1)
            ob.hide_render = not start_hidden
            ob.keyframe_insert("hide_render", frame=int(round(fr(t_hide))))
    finally:
        prefs.keyframe_new_interpolation_type = old
