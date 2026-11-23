# -*- coding: utf-8 -*-
# Material builders (exec'd after tbv_cfg.py in the same namespace). Every datablock is prefixed TBV_.
import bpy, os

def clear_tbv():
    """remove everything this build created (only TBV_* datablocks)"""
    for ob in list(bpy.data.objects):
        if ob.name.startswith("TBV_"):
            bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras,
                 bpy.data.curves, bpy.data.node_groups, bpy.data.collections, bpy.data.worlds):
        for d in list(coll):
            if d.name.startswith("TBV_"):
                coll.remove(d)
    for im in list(bpy.data.images):
        if im.name.startswith("TBV_"):
            bpy.data.images.remove(im)
    for a in list(bpy.data.actions):
        if a.users == 0:
            bpy.data.actions.remove(a)

def get_coll(name, parent=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c

def load_img(path, alpha=False):
    if not path or not os.path.exists(path):
        if path:
            print("!! missing texture, using plain paper:", path)
        return None
    key = "TBV_" + os.path.basename(path)
    im = bpy.data.images.get(key)
    if im is None or bpy.path.abspath(im.filepath) != path:
        im = bpy.data.images.load(path, check_existing=False)
        im.name = key
    im.alpha_mode = 'STRAIGHT' if alpha else 'NONE'
    return im

def _sock(node, ident, out=False):
    for s in (node.outputs if out else node.inputs):
        if s.identifier == ident or s.name == ident:
            return s
    raise KeyError(ident)

def _new_mat(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (600, 0)
    return m, nt, out

def _paper_bump(nt, bsdf, scale=1800.0, strength=0.035):
    noise = nt.nodes.new("ShaderNodeTexNoise"); noise.location = (-500, -300)
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 4.0
    bump = nt.nodes.new("ShaderNodeBump"); bump.location = (-200, -300)
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = 0.0003
    nt.links.new(_sock(noise, "Fac", True), bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

PAPER_TINT = (0.985, 0.972, 0.940)

def mat_paper(name, path, mirror=False, tint=PAPER_TINT, rough=0.78):
    """printed page: texture * warm paper tint, low gloss, paper-grain bump"""
    m, nt, out = _new_mat(name)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (250, 0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Specular IOR Level"].default_value = 0.25
    im = load_img(path)
    if im is not None:
        tc = nt.nodes.new("ShaderNodeTexCoord"); tc.location = (-900, 0)
        src = _sock(tc, "UV", True)
        if mirror:
            mp = nt.nodes.new("ShaderNodeMapping"); mp.location = (-700, 0)
            mp.inputs["Location"].default_value = (1.0, 0.0, 0.0)
            mp.inputs["Scale"].default_value = (-1.0, 1.0, 1.0)
            nt.links.new(src, mp.inputs["Vector"]); src = mp.outputs["Vector"]
        ti = nt.nodes.new("ShaderNodeTexImage"); ti.location = (-500, 100)
        ti.image = im; ti.interpolation = 'Linear'; ti.extension = 'EXTEND'
        nt.links.new(src, ti.inputs["Vector"])
        mul = nt.nodes.new("ShaderNodeVectorMath"); mul.location = (-150, 100)
        mul.operation = 'MULTIPLY'
        mul.inputs[1].default_value = tint
        nt.links.new(_sock(ti, "Color", True), mul.inputs[0])
        nt.links.new(mul.outputs[0], bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (tint[0] * 0.97, tint[1] * 0.97, tint[2] * 0.97, 1)
    _paper_bump(nt, bsdf)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m

def mat_simple(name, color, rough=0.6, spec=0.3, metallic=0.0):
    m, nt, out = _new_mat(name)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (250, 0)
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Specular IOR Level"].default_value = spec
    bsdf.inputs["Metallic"].default_value = metallic
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m

def mat_cloth_board(name, color):
    """book-cloth board edge / spine: fine weave bump"""
    m = mat_simple(name, color, rough=0.72, spec=0.2)
    nt = m.node_tree
    bsdf = [n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"][0]
    _paper_bump(nt, bsdf, scale=2600.0, strength=0.08)
    return m

def mat_edges(name):
    """page-block side faces: thin horizontal paper lines (world-space so block scaling doesn't squash them)"""
    m, nt, out = _new_mat(name)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (250, 0)
    bsdf.inputs["Roughness"].default_value = 0.85
    bsdf.inputs["Specular IOR Level"].default_value = 0.15
    geo = nt.nodes.new("ShaderNodeNewGeometry"); geo.location = (-900, 0)
    wave = nt.nodes.new("ShaderNodeTexWave"); wave.location = (-650, 0)
    wave.wave_type = 'BANDS'; wave.bands_direction = 'Z'
    wave.inputs["Scale"].default_value = 0.8
    wave.inputs["Distortion"].default_value = 1.5
    wave.inputs["Detail"].default_value = 2.0
    mapn = nt.nodes.new("ShaderNodeMapping"); mapn.location = (-780, 0)
    mapn.inputs["Scale"].default_value = (40.0, 40.0, 1500.0)
    nt.links.new(geo.outputs["Position"], mapn.inputs["Vector"])
    nt.links.new(mapn.outputs["Vector"], wave.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB"); ramp.location = (-350, 0)
    ramp.color_ramp.elements[0].color = (0.80, 0.78, 0.74, 1)
    ramp.color_ramp.elements[1].color = (0.95, 0.94, 0.91, 1)
    nt.links.new(_sock(wave, "Fac", True), ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m

def mat_highlight(name, color=(0.91, 0.33, 0.30)):
    """marker pen: coloured transparency == multiply over the paper, black ink stays black"""
    m, nt, out = _new_mat(name)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent"); tr.location = (250, 0)
    tr.inputs["Color"].default_value = (*color, 1)
    nt.links.new(tr.outputs["BSDF"], out.inputs["Surface"])
    m.surface_render_method = 'BLENDED'
    m.use_transparent_shadow = True
    m.use_backface_culling = False
    return m

def mat_card(name, path, tint=(1.0, 1.0, 1.0), cull=True):
    """paper-cut illustration card with alpha cut-out (grey placeholder without an image)"""
    m, nt, out = _new_mat(name)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (250, 0)
    bsdf.inputs["Roughness"].default_value = 0.88
    bsdf.inputs["Specular IOR Level"].default_value = 0.2
    im = load_img(path, alpha=True)
    if im is not None:
        ti = nt.nodes.new("ShaderNodeTexImage"); ti.location = (-500, 100)
        ti.image = im; ti.interpolation = 'Linear'; ti.extension = 'CLIP'
        mul = nt.nodes.new("ShaderNodeVectorMath"); mul.location = (-150, 100)
        mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = tint
        nt.links.new(_sock(ti, "Color", True), mul.inputs[0])
        nt.links.new(mul.outputs[0], bsdf.inputs["Base Color"])
        nt.links.new(_sock(ti, "Alpha", True), bsdf.inputs["Alpha"])
    else:
        bsdf.inputs["Base Color"].default_value = (0.45 * tint[0], 0.45 * tint[1], 0.45 * tint[2], 1)
    _paper_bump(nt, bsdf, scale=1400.0, strength=0.05)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    m.surface_render_method = 'DITHERED'
    m.use_transparent_shadow = True
    m.use_backface_culling = cull
    return m

def mat_fruit(name, color=(0.807, 0.184, 0.027)):
    m = mat_simple(name, color, rough=0.42, spec=0.45)
    nt = m.node_tree
    bsdf = [n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"][0]
    bsdf.inputs["Subsurface Weight"].default_value = 0.08
    _paper_bump(nt, bsdf, scale=9000.0, strength=0.25)
    return m

def _srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def cover_edge_colour(path, default=(0.127, 0.215, 0.204)):
    """median colour of the cover's spine-side strip (left 1-4 %), linear RGB, slightly darkened"""
    if PROJ.get("book", {}).get("cloth"):
        return tuple(PROJ["book"]["cloth"])
    im = load_img(path)
    if im is None:
        return default
    try:
        import numpy as np
        w, h = im.size
        a = np.empty(w * h * 4, dtype=np.float32)
        im.pixels.foreach_get(a)
        a = a.reshape(h, w, 4)[int(0.1 * h):int(0.9 * h), int(0.01 * w):max(int(0.01 * w) + 1, int(0.04 * w)), :3]
        med = np.median(a.reshape(-1, 3), axis=0)
        return tuple(_srgb_to_lin(float(c)) * 0.85 for c in med)
    except Exception as e:  # never fail the build for a cosmetic colour
        print("!! cover edge colour fallback:", e)
        return default
