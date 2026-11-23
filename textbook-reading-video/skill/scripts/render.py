#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headless Blender rendering of DIR/blender/scene.blend.

  render.py --project DIR --test 1,61,150,600 [--percent 50] [--samples 16]   # blocking stills -> DIR/render/test
  render.py --project DIR [--procs 2] [--percent 100] [--samples N] [--fresh|--resume]   # detached full render
  render.py --project DIR --status                                            # progress / ETA
  render.py --project DIR --wait [--timeout 1500]                             # block until done (or timeout)

The full render starts its Blender processes in their own sessions (they survive the calling shell) and
skips frames that already exist, so re-running it resumes. If scene.blend is newer than the existing
frames it refuses: --fresh moves the old frames aside, --resume keeps them.
Frames: DIR/<render.frames_dir>/0001.png ...
"""
import argparse, glob, json, os, subprocess, sys, time

BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")

def load(root):
    with open(os.path.join(root, "project.json"), encoding="utf-8") as f:
        return json.load(f)

def setup_script(path, percent=None, samples=None, filepath=None, resume=False):
    lines = ["import bpy", "s = bpy.data.scenes['TBV'] if 'TBV' in bpy.data.scenes else bpy.context.scene"]
    if percent: lines.append(f"s.render.resolution_percentage = {int(percent)}")
    if samples: lines.append(f"s.eevee.taa_render_samples = {int(samples)}")
    if filepath: lines.append(f"s.render.filepath = {filepath!r}")
    if resume: lines += ["s.render.use_overwrite = False", "s.render.use_placeholder = False"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def frames_done(fdir, n):
    return sorted(k for k in range(1, n + 1) if os.path.exists(os.path.join(fdir, f"{k:04d}.png")))

def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--blend")
    ap.add_argument("--test")
    ap.add_argument("--percent", type=int)
    ap.add_argument("--samples", type=int)
    ap.add_argument("--procs", type=int, default=2)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--wait", action="store_true")
    ap.add_argument("--timeout", type=float, default=1500)
    ap.add_argument("--fresh", action="store_true", help="move existing frames aside (frames.bak.<time>) first")
    ap.add_argument("--resume", action="store_true", help="keep existing frames even if scene.blend is newer")
    a = ap.parse_args()
    root = os.path.abspath(a.project)
    cfg = load(root)
    blend = a.blend or os.path.join(root, "blender", "scene.blend")
    n = int(round(float(cfg["duration"]) * int(cfg.get("fps", 30))))
    fdir = os.path.join(root, (cfg.get("render") or {}).get("frames_dir", "render/frames"))
    logs = os.path.join(root, "render", "logs")
    os.makedirs(fdir, exist_ok=True); os.makedirs(logs, exist_ok=True)
    jobs_p = os.path.join(logs, "jobs.json")
    if a.test:
        out = os.path.join(root, "render", "test"); os.makedirs(out, exist_ok=True)
        sp = os.path.join(out, "_setup.py")
        setup_script(sp, a.percent or 50, a.samples or 16, os.path.join(out, "t_####"))
        t0 = time.time()
        r = subprocess.run([BLENDER, "-b", blend, "--python", sp, "-f", a.test], capture_output=True, text=True)
        bad = [l for l in (r.stdout + r.stderr).splitlines() if "Error" in l or "Traceback" in l]
        for k in a.test.split(","):
            p = os.path.join(out, f"t_{int(k):04d}.png")
            print(p if os.path.exists(p) else f"MISSING {p}")
        print(f"elapsed {time.time() - t0:.1f}s", *bad[-8:], sep="\n")
        sys.exit(1 if r.returncode or bad else 0)
    if a.status or a.wait:
        t_end = time.time() + a.timeout
        while True:
            done = frames_done(fdir, n)
            jobs = json.load(open(jobs_p)) if os.path.exists(jobs_p) else {"pids": [], "t0": time.time(), "n0": 0}
            run = [p for p in jobs["pids"] if alive(p)]
            rate = (len(done) - jobs.get("n0", 0)) / max(1.0, time.time() - jobs["t0"])
            eta = (n - len(done)) / rate if rate > 0 else float("nan")
            print(f"frames {len(done)}/{n}  running procs {len(run)}  {rate * 60:.1f} f/min  ETA {eta / 60:.1f} min", flush=True)
            if not a.wait or len(done) >= n or not run or time.time() > t_end:
                sys.exit(0 if len(done) >= n else (3 if not run else 2))
            time.sleep(30)
    have = frames_done(fdir, n)
    if have and a.fresh:
        bak = fdir.rstrip("/") + time.strftime(".bak.%Y%m%d%H%M%S")
        os.rename(fdir, bak); os.makedirs(fdir)
        print(f"moved {len(have)} old frames to {bak}")
        have = []
    elif have and not a.resume:
        newest = max(os.path.getmtime(os.path.join(fdir, f"{k:04d}.png")) for k in have)
        if os.path.getmtime(blend) > newest:
            sys.exit(f"{blend} is newer than the {len(have)} frames in {fdir}: "
                     "pass --fresh (moves them aside) or --resume (keeps them)")
    if len(have) >= n:
        print(f"all {n} frames already rendered in {fdir}"); return
    sp = os.path.join(logs, "_resume.py")
    setup_script(sp, a.percent, a.samples, os.path.join(fdir, "####"), resume=True)
    todo = [k for k in range(1, n + 1) if k not in set(have)]
    s0, e0 = todo[0], n
    per = (e0 - s0 + 1 + a.procs - 1) // a.procs
    pids = []
    for k in range(a.procs):
        s, e = s0 + k * per, min(e0, s0 + (k + 1) * per - 1)
        if s > e:
            continue
        log = open(os.path.join(logs, f"render_{k}_{int(time.time())}.log"), "w")
        p = subprocess.Popen([BLENDER, "-b", blend, "--python", sp, "-s", str(s), "-e", str(e), "-a"],
                             stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             start_new_session=True, close_fds=True)
        pids.append(p.pid)
        print(f"proc {k}: frames {s}-{e} pid {p.pid}", flush=True)
        if k == 0 and a.procs > 1:
            time.sleep(15)      # stagger the shader compilation
    json.dump({"pids": pids, "t0": time.time(), "n0": len(have), "n": n}, open(jobs_p, "w"))
    print(f"started; poll with: render.py --project {root!r} --status")

if __name__ == "__main__":
    main()
