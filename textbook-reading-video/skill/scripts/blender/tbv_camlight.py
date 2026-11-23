# -*- coding: utf-8 -*-
# Camera rig + keys (intro fixed, reading keys from the timeline), lights, world, ground, render settings
import bpy, math, os
from mathutils import Vector

def toc_center():
    th = PROJ.get("toc_highlight")
    if not (HAS_TOC and th):
        return None
    return page_xy(0.5 * (th["x0"] + th["x1"]), th["line_top"] + 0.5 * th["line_h"], "toc")

def cam_keys():
    """(t, aim x, aim y, aim z, tilt deg, yaw deg, distance, f-stop)"""
    K = [(0.00, 0.050, 0.004, 0.0150, 27.0, 9.0, 1.02, 5.6),
         (1.00, 0.042, 0.002, 0.0145, 26.0, 8.0, 0.96, 5.6),
         (1.90, 0.000, 0.000, 0.0080, 22.0, 5.0, 0.80, 5.6)]
    tc = toc_center()
    if tc:     # push in on the article's TOC entry while it is highlighted (2.55-3.05 s)
        K += [(2.70, tc[0] - 0.012, tc[1] + 0.012, 0.0110, 18.0, 3.0, 0.52, 6.3),
              (3.25, tc[0], tc[1], 0.0110, 17.0, 2.0, 0.46, 6.3)]
    else:      # no TOC page: a gentle push over the right page instead
        K += [(2.70, 0.055, 0.000, 0.0100, 19.0, 3.0, 0.62, 6.3),
              (3.25, 0.065, -0.008, 0.0100, 18.0, 2.0, 0.58, 6.3)]
    K.append((3.90, 0.060, -0.005, 0.0090, 18.0, 1.0, 0.60, 6.3))
    x0, y0, z0 = _target_at(T_READ0)
    sx = 1.0 if x0 >= 0 else -1.0
    K.append((4.40, x0 - 0.0025 * sx, y0 - 0.016, z0, 16.0, 0.0, 0.44, 8.0))
    # reading: smoothed follow of the highlighted row, slow push-in / pull-out and a little sway.
    # Distance fits the text block width: 91 % of the frame width at the start/end, 94 % in the middle.
    d_fit = min(0.32, max(0.20, text_width(READ_PAGE) / (36.0 / 55.0 * 0.94)))
    ta, tb = T_READ0 - 0.1, max(T_READ0 + 0.5, T_READ1 - 0.3)
    n = max(2, int(math.ceil((tb - ta) / 0.4)))
    for k in range(n + 1):
        t = ta + (tb - ta) * k / n
        u = clamp01((t - T_READ0) / max(1e-3, T_READ1 - T_READ0))
        x, y, z = reading_target(t)
        x += 0.0010 * math.sin(2 * math.pi * 1.5 * u) - 0.0005
        K.append((t, x, y, z, 9.0 - 0.5 * math.sin(math.pi * u), 0.0, d_fit * (1.035 - 0.035 * math.sin(math.pi * u)), 11.0))
    # outro: pull back to the open book
    K.append((max(tb + 0.6, DURATION - 0.30), 0.002, -0.004, 0.0080, 20.0, 0.0, 0.700, 8.0))
    K.append((max(tb + 0.9, DURATION), 0.001, -0.004, 0.0080, 20.0, 0.0, 0.708, 8.0))
    return K

CAM_KEYS = cam_keys()

def _look_rot(src, dst):
    d = Vector(dst) - Vector(src)
    return d.to_track_quat('-Z', 'Y').to_euler()

def build_world_and_lights():
    coll = get_coll("TBV_Env")
    w = bpy.data.worlds.get("TBV_World") or bpy.data.worlds.new("TBV_World")
    w.use_nodes = True
    wnt = w.node_tree
    for nd in list(wnt.nodes):
        wnt.nodes.remove(nd)
    bg = wnt.nodes.new("ShaderNodeBackground")
    wout = wnt.nodes.new("ShaderNodeOutputWorld"); wout.location = (300, 0)
    wnt.links.new(bg.outputs["Background"], wout.inputs["Surface"])
    bg.inputs["Color"].default_value = (0.0060, 0.0070, 0.0065, 1)     # ~#121413 on screen
    bg.inputs["Strength"].default_value = 1.0
    bpy.context.scene.world = w
    me = bpy.data.meshes.new("TBV_Ground")
    s = 2.0
    me.from_pydata([(-s, -s, -0.0002), (s, -s, -0.0002), (s, s, -0.0002), (-s, s, -0.0002)], [], [(0, 1, 2, 3)])
    me.materials.append(mat_simple("TBV_M_ground", (0.0052, 0.0062, 0.0056), rough=0.95, spec=0.1))
    gr = bpy.data.objects.new("TBV_Ground", me); coll.objects.link(gr)
    L = {}
    def add(name, kind, loc, aim, energy, color, size=None, angle=None):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy; ld.color = color
        if size is not None:
            ld.shape = 'RECTANGLE'; ld.size = size; ld.size_y = size * 0.7
        if angle is not None:
            ld.angle = math.radians(angle)
        ld.use_shadow = True
        ob = bpy.data.objects.new(name, ld); coll.objects.link(ob)
        ob.location = loc; ob.rotation_euler = _look_rot(loc, aim)
        L[name] = ob
        return ob
    add("TBV_Key", 'SUN', (-0.45, -0.55, 0.90), (0, 0, 0), 1.38, (1.0, 0.975, 0.94), angle=7.0)
    add("TBV_Rim", 'AREA', (0.55, 0.75, 0.30), (0.05, 0.0, 0.01), 11.0, (1.0, 0.93, 0.84), size=0.6)
    add("TBV_Fill", 'AREA', (0.60, -0.70, 0.80), (0.05, 0.0, 0.0), 5.5, (0.92, 0.96, 1.0), size=1.2)
    return L

def build_camera():
    coll = get_coll("TBV_Cam")
    rig = bpy.data.objects.new("TBV_CamRig", None); coll.objects.link(rig)
    rig.empty_display_type = 'SPHERE'; rig.empty_display_size = 0.004
    cd = bpy.data.cameras.new("TBV_Camera")
    cd.lens = 55.0; cd.sensor_fit = 'HORIZONTAL'; cd.sensor_width = 36.0
    cd.clip_start = 0.01; cd.clip_end = 20.0
    cd.dof.use_dof = True; cd.dof.focus_object = rig
    cam = bpy.data.objects.new("TBV_Camera", cd); coll.objects.link(cam)
    cam.parent = rig
    bpy.context.scene.camera = cam
    prefs = bpy.context.preferences.edit
    old_i, old_h = prefs.keyframe_new_interpolation_type, prefs.keyframe_new_handle_type
    prefs.keyframe_new_interpolation_type = 'BEZIER'; prefs.keyframe_new_handle_type = 'AUTO_CLAMPED'
    try:
        for (t, ax, ay, az, tilt, yaw, d, fs) in CAM_KEYS:
            f = fr(t)
            rig.location = (ax, ay, az)
            rig.rotation_euler = (math.radians(tilt), 0.0, math.radians(yaw))
            cam.location = (0.0, 0.0, d)
            cd.dof.aperture_fstop = fs
            rig.keyframe_insert("location", frame=f)
            rig.keyframe_insert("rotation_euler", frame=f)
            cam.keyframe_insert("location", index=2, frame=f)
            cd.dof.keyframe_insert("aperture_fstop", frame=f)
    finally:
        prefs.keyframe_new_interpolation_type, prefs.keyframe_new_handle_type = old_i, old_h
    return rig, cam

def setup_render(samples=32, percent=100):
    s = bpy.context.scene
    r = s.render
    r.engine = 'BLENDER_EEVEE'
    r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, int(percent)
    r.fps = FPS; s.frame_start = 1; s.frame_end = NFRAMES
    r.filter_size = 1.2
    r.image_settings.file_format = 'PNG'
    r.image_settings.color_mode = 'RGB'
    r.image_settings.color_depth = '8'
    r.image_settings.compression = 15
    fd = (PROJ.get("render") or {}).get("frames_dir", "render/frames")
    r.filepath = os.path.join(P, fd, "####")
    r.use_motion_blur = False
    e = s.eevee
    e.taa_render_samples = int(samples)
    e.use_shadows = True
    e.shadow_ray_count = 2
    e.shadow_step_count = 8
    e.use_raytracing = False
    e.use_fast_gi = False
    s.display_settings.display_device = 'sRGB'
    s.view_settings.view_transform = 'Standard'
    s.view_settings.look = 'None'
    s.view_settings.exposure = 0.0
    s.view_settings.gamma = 1.0
