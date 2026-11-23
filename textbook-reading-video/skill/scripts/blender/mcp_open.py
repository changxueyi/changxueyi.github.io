# -*- coding: utf-8 -*-
# Open a built scene in the user's live Blender through MCP (execute_blender_code).
# Prepend:  BLEND = "/abs/path/DIR/blender/scene.blend"
# Unsaved work in the current session is first saved as a copy next to the scene (nothing is lost),
# then the file is opened from a timer so the MCP reply is sent before the load; the MCP add-on
# restarts its server after the load (wait ~2 s before the next call).
import bpy, os, time

_blend = os.path.abspath(BLEND)
if not os.path.exists(_blend):
    raise FileNotFoundError(_blend)
if bpy.data.is_dirty:
    _bak = os.path.join(os.path.dirname(_blend), "_previous_session_%s.blend" % time.strftime("%Y%m%d%H%M%S"))
    bpy.ops.wm.save_as_mainfile(filepath=_bak, copy=True)
    print("unsaved session copied to", _bak)

def _tbv_open():
    bpy.ops.wm.open_mainfile(filepath=_blend)
    return None

bpy.app.timers.register(_tbv_open, first_interval=0.3)
print("opening", _blend, "(previous file:", bpy.data.filepath or "untitled", ")")
