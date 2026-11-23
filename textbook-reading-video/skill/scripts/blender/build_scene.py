# -*- coding: utf-8 -*-
"""Build the 3D textbook scene from project.json (headless, fresh factory scene) and save it.

  Blender -b --factory-startup --python build_scene.py -- --project DIR [--samples 32] [--percent 100]
          [--out DIR/blender/scene.blend] [--no-verify]

Writes DIR/blender/scene.blend (scene "TBV", texture paths relative) and DIR/blender/verify.json.
Requires project.json with pages/book/fillers (init_project.py), reading (align.py),
timeline/duration (narrate.py). Cards/props are optional.
"""
import bpy, os, sys, time, json

def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    a = {"project": None, "samples": None, "percent": None, "out": None, "verify": True}
    k = 0
    while k < len(argv):
        x = argv[k]
        if x == "--project": a["project"] = argv[k + 1]; k += 2
        elif x == "--samples": a["samples"] = int(argv[k + 1]); k += 2
        elif x == "--percent": a["percent"] = int(argv[k + 1]); k += 2
        elif x == "--out": a["out"] = argv[k + 1]; k += 2
        elif x == "--no-verify": a["verify"] = False; k += 1
        else: raise SystemExit(f"unknown argument {x}")
    if not a["project"]:
        raise SystemExit("--project DIR is required")
    return a

HERE = os.path.dirname(os.path.abspath(__file__))
MODULES = ["tbv_cfg.py", "tbv_materials.py", "tbv_book.py", "tbv_camlight.py",
           "tbv_overlays.py", "tbv_cards.py", "tbv_verify.py"]

def load_modules(ns, project_dir):
    ns["PROJECT_DIR"] = os.path.abspath(project_dir)
    for f in MODULES:
        p = os.path.join(HERE, f)
        exec(compile(open(p, encoding="utf-8").read(), p, "exec"), ns)
    return ns

def main():
    if not bpy.app.background:
        raise SystemExit("build_scene.py is meant for headless Blender (-b --factory-startup); "
                         "open the saved scene.blend in the live Blender instead")
    a = _args()
    t_start = time.time()
    ns = load_modules(globals(), a["project"])
    req = [k for k in ("reading", "timeline", "duration", "pages", "book") if not ns["PROJ"].get(k)]
    if req:
        raise SystemExit(f"project.json lacks {req}: run init_project.py / align.py / narrate.py first")
    scn = bpy.context.scene
    scn.name = "TBV"
    for ob in list(bpy.data.objects):          # factory cube / light / camera
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for d in list(coll):
            if d.users == 0:
                coll.remove(d)
    clear_tbv()
    scn.frame_set(1)
    build_book(); bake_intro()
    build_world_and_lights()
    build_camera()
    bands = build_bands()
    C = build_cards()
    rd = PROJ.get("render") or {}
    setup_render(samples=a["samples"] or rd.get("samples", 32), percent=a["percent"] or rd.get("percent", 100))
    scn.frame_set(1)
    out = a["out"] or os.path.join(P, "blender", "scene.blend")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=out)
    try:
        bpy.ops.file.make_paths_relative()
        bpy.ops.wm.save_mainfile()
    except Exception as e:
        print("!! make_paths_relative failed (absolute texture paths kept):", e)
    info = {"blend": out, "frames": NFRAMES, "duration": DURATION, "bands": len(bands),
            "cards": len(C["cards"]) if C else 0, "props": len(C["props"]) if C else 0,
            "read_page": READ_PAGE, "has_toc": HAS_TOC, "cam_keys": len(CAM_KEYS)}
    if a["verify"]:
        rep = report(os.path.join(P, "blender", "verify.json"))
        info["warnings"] = rep["warnings"]
        info["toc_band_screen"] = rep["toc"]
    info["seconds"] = round(time.time() - t_start, 1)
    print("TBV_BUILD " + json.dumps(info, ensure_ascii=False))

main()
