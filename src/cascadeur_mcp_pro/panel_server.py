"""Tools Pro companion web panel — a styled local page that drives Cascadeur
through the MCP bridge. Full custom style (unlike the built-in DialogManager
windows), live scene status, and richer controls. Run:  python run_panel.py

Endpoints:
  GET  /            -> the panel page (panel.html)
  GET  /status      -> {connected, character, frames, tabs}
  POST /browse      -> {path}  (native OS file dialog, run as a subprocess)
  POST /action      -> {summary} | {error}  (rig / retarget / physics_fill /
                       export / cleanup_tabs — orchestrated over the bridge)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .bridge_client import BridgeClient, BridgeError
from . import fbx_writer

_HERE = os.path.dirname(os.path.abspath(__file__))
bridge = BridgeClient()


# --------------------------------------------------------------- action logic

def _status():
    try:
        info, _ = bridge.run_op("scene.info")
        return {"connected": True,
                "character": info.get("name"),
                "frames": info.get("animation_frames"),
                "tabs": len(info.get("tabs", []) or [])}
    except Exception as e:
        return {"connected": False, "error": str(e)[:120]}


def _pick_file(save=False):
    code = (
        "import tkinter, tkinter.filedialog as fd\n"
        "r=tkinter.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
        "p=(fd.asksaveasfilename() if %s else "
        "fd.askopenfilename(filetypes=[('FBX','*.fbx'),('All files','*.*')]))\n"
        "print(p or '')\n" % bool(save))
    try:
        out = subprocess.run([sys.executable, "-c", code],
                             capture_output=True, text=True, timeout=180)
        return out.stdout.strip()
    except Exception:
        return ""


def _parse_clips(text, last):
    text = (text or "").strip()
    if not text:
        return [("take", 0, last)]
    clips = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, rng = chunk.partition(":")
        a, _, b = rng.partition("-")
        clips.append((name.strip() or "clip",
                      int(a.strip() or 0),
                      int(b.strip()) if b.strip() else last))
    return clips


def _act_rig(args):
    path = args["path"]
    with bridge.session():
        bridge.run_op("scene.close_others")
        bridge.run_op("fbx.import", {"path": path, "mode": "model",
                                     "new_scene": True})
        bm, _ = bridge.run_op("rig.bone_map")
        rig, _ = bridge.run_op("rig.quick_rig",
                               {"template": "Mixamo_Namespace_Template_New",
                                "autoposing": True, "open_tool": False})
    r = rig.get("rig", {}) if isinstance(rig, dict) else {}
    roles = bm.get("roles", {}) or {}
    return {"summary": "rigged: %s joints, %s controllers, %d roles, fingers %s"
            % (r.get("joint_count", "?"), r.get("point_controllers", "?"),
               len(roles), "yes" if (bm.get("fingers") or
                                     bm.get("finger_summary")) else "no")}


def _roles_hip():
    bm, _ = bridge.run_op("rig.bone_map")
    roles = {r: d.get("joint") for r, d in (bm.get("roles", {}) or {}).items()}
    hip = None
    hips = (bm.get("roles", {}) or {}).get("hips")
    if hips and hips.get("world_position"):
        hip = hips["world_position"][1]
    return roles, hip, bm


def _act_retarget(args):
    path = args["path"]
    with bridge.session():
        tgt_info, _ = bridge.run_op("scene.info")
        target_tab = tgt_info.get("name")
        tgt_roles, _h, _ = _roles_hip()
        tgt_suffixes = {j.split(":")[-1] for j in tgt_roles.values() if j}

        bridge.run_op("fbx.import", {"path": path, "mode": "scene",
                                     "new_scene": True})
        src_roles, src_hip, _ = _roles_hip()
        bake, _ = bridge.run_op("anim.bake")
        src_joints = [{"name": j["name"], "frames": j["frames"]}
                      for j in bake["joints"]]
        src_suffixes = {n.split(":")[-1] for n in src_roles.values() if n}
        overlap = len(src_suffixes & tgt_suffixes)
        mode = "name" if overlap >= max(6, len(tgt_suffixes) // 2) else "role"

        bridge.run_op("scene.switch_tab", {"name": target_tab})
        bridge.run_op("scene.set_clip_length", {"frames": bake["frame_count"] + 2})
        res, _ = bridge.run_op("anim.retarget",
                               {"source_joints": src_joints,
                                "source_roles": src_roles,
                                "source_hip_height": src_hip, "match": mode})
        try:
            bridge.run_op("scene.close_others", {"keep": target_tab})
        except BridgeError:
            pass
    applied = res.get("applied_joints") or res.get("joints") or 0
    extra = ""
    if res.get("match") == "role":
        extra = " (%d roles, root x%s)" % (res.get("matched_roles", 0),
                                           res.get("hip_scale"))
    return {"summary": "retargeted %d bones by %s%s"
            % (applied, res.get("match", mode), extra)}


def _act_physics_fill(args):
    with bridge.session():
        info, _ = bridge.run_op("scene.info")
        last = max(int(info.get("animation_frames", 1)) - 1, 1)
        bm, _ = bridge.run_op("rig.bone_map")
        feet = []
        for r, d in (bm.get("roles", {}) or {}).items():
            if any(h in r for h in ("foot", "toe", "ankle", "heel")):
                mp = (d.get("controllers") or {}).get("MainPoint")
                if mp:
                    feet.append(mp.split(":")[-1])
        step = max(1, last // 20)
        for f in range(0, last + 1, step):
            try:
                bridge.run_op("interval.set", {"frame": f, "interpolation": "BEZIER"})
            except BridgeError:
                pass
        if feet:
            for f in range(0, last + 1, step):
                try:
                    bridge.run_op("interval.set", {"frame": f, "ik_fk": "IK",
                                                   "fixation": "fulcrum",
                                                   "object_names": feet})
                except BridgeError:
                    pass
        tweened = 0
        for f in range(1, last, max(1, last // 8)):
            try:
                bridge.run_op("ai.physics_tween", {"frame": f,
                                                   "mode": "Interpolation",
                                                   "factor": 0.5})
                tweened += 1
            except BridgeError:
                pass
    return {"summary": "spline+IK/fulcrum(%d feet)+attractor(%d frames)"
            % (len(feet), tweened)}


def _act_export(args):
    base = (args.get("base") or "").replace("\\", "/")
    if base.lower().endswith(".fbx"):
        base = base[:-4]
    if not base:
        return {"error": "no output path"}
    os.makedirs(os.path.dirname(base) or ".", exist_ok=True)
    with bridge.session():
        info, _ = bridge.run_op("scene.info")
        last = max(int(info.get("animation_frames", 1)) - 1, 1)
        clips = _parse_clips(args.get("clips"), last)
        written = []
        for name, s, e in clips:
            bake, _ = bridge.run_op("anim.bake", {"frame_start": s,
                                                  "frame_end": e + 1})
            if bake.get("joint_count", 0) == 0:
                continue
            safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
            p = "%s@%s.fbx" % (base, safe)
            fbx_writer.write_fbx_ascii(bake, p)
            written.append(os.path.basename(p))
    return {"summary": "wrote %d clip(s): %s" % (len(written), ", ".join(written))}


def _act_cleanup(args):
    r, _ = bridge.run_op("scene.close_others")
    return {"summary": "closed %d tab(s), %d left"
            % (r.get("closed_count", 0), r.get("remaining", 1))}


_ACTIONS = {
    "rig": _act_rig, "retarget": _act_retarget, "physics_fill": _act_physics_fill,
    "export": _act_export, "cleanup_tabs": _act_cleanup,
}


# ------------------------------------------------------------------- HTTP

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(_HERE, "panel.html"), "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/status":
            self._json(_status())
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        data = self._body()
        if self.path == "/browse":
            self._json({"path": _pick_file(bool(data.get("save")))})
        elif self.path == "/action":
            fn = _ACTIONS.get(data.get("action"))
            if not fn:
                return self._json({"error": "unknown action"})
            try:
                self._json(fn(data.get("args", {}) or {}))
            except BridgeError as e:
                self._json({"error": str(e)[:400]})
            except Exception as e:
                import traceback
                self._json({"error": traceback.format_exc()[-400:]})
        else:
            self._json({"error": "not found"}, 404)


def main(port=8765, open_browser=True):
    srv = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    url = "http://127.0.0.1:%d/" % port
    print("Tools Pro panel: %s   (Ctrl+C to stop)" % url)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        srv.shutdown()


if __name__ == "__main__":
    main()
