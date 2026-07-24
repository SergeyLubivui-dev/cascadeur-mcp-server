"""cascadeur-mcp-pro: deep MCP integration for Cascadeur.

Tools talk to a bridge command installed inside Cascadeur (see
cascadeur_side/mcp_bridge). Each tool call opens one short bridge session on
Cascadeur's main thread; multiple ops can be batched into a single session.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from mcp.server.fastmcp import FastMCP, Image

from .bridge_client import BridgeClient, BridgeError
from . import dataset, rigmodel, physics

mcp = FastMCP(
    "cascadeur",
    instructions=(
        "Control the running Cascadeur instance: scenes, FBX import/export, rig "
        "and skeleton inspection, per-frame transforms, keyframes and "
        "interpolation, mirror, undo/redo, viewport screenshots. Use "
        "cascadeur_api_search to look up Cascadeur's Python API before writing "
        "code for cascadeur_run_python."
    ),
)

bridge = BridgeClient()


def _call(op: str, args: dict | None = None) -> Any:
    try:
        result, stdout = bridge.run_op(op, args)
    except BridgeError as e:
        return {"error": str(e)}
    if stdout:
        return {"result": result, "stdout": stdout}
    return result


# ------------------------------------------------------------------ meta


@mcp.tool()
def cascadeur_status() -> dict:
    """Check the connection to Cascadeur: bridge health, latency, scene summary."""
    try:
        result, _ = bridge.run_op("scene.info")
        return {
            "connected": True,
            "cascadeur_exe": bridge.cascadeur_exe(),
            "bridge_latency_sec": round(bridge.last_latency or -1, 2),
            "scene": result,
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}


@mcp.tool()
def cascadeur_run_python(code: str, reload_ops: bool = False) -> dict:
    """Execute Python inside Cascadeur with `csc`, `scene` (domain scene), `app`
    and `pycsc` in scope. Set a `result` variable to return JSON-serialisable data.
    Runs on the main thread; wrap scene mutations in scene.modify_update(...).
    Use cascadeur_api_search first to check API signatures."""
    try:
        result, stdout = bridge.run_op("python.exec", {"code": code},
                                       reload_ops=reload_ops)
        return {"result": result, "stdout": stdout or ""}
    except BridgeError as e:
        return {"error": str(e)}


@mcp.tool()
def cascadeur_api_search(query: str, max_results: int = 8,
                         context_lines: int = 12) -> dict:
    """Search Cascadeur's bundled Python API documentation and scripts
    (api_document.py, pycsc wrapper, samples, rig scripts) by regex.
    Use before writing cascadeur_run_python code. Examples of good queries:
    'set_data_value', 'FbxLoader', 'class Rotation', 'modify_update'."""
    try:
        scripts_root = os.path.join(
            os.path.dirname(bridge.cascadeur_exe()), "resources", "scripts", "python")
    except BridgeError as e:
        return {"error": str(e)}
    targets = []
    for rel in ("samples", "pycsc", "common", "rig_mode", "commands",
                "prototypes", "fbx_import"):
        base = os.path.join(scripts_root, rel)
        for dirpath, _dirnames, filenames in os.walk(base):
            for fn in filenames:
                if fn.endswith(".py"):
                    targets.append(os.path.join(dirpath, fn))
    rx = re.compile(query, re.IGNORECASE)
    hits = []
    for path in targets:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            if rx.search(line):
                lo = max(0, i - 2)
                hi = min(len(lines), i + context_lines)
                hits.append({
                    "file": os.path.relpath(path, scripts_root),
                    "line": i + 1,
                    "snippet": "".join(lines[lo:hi]),
                })
                if len(hits) >= max_results:
                    return {"query": query, "hits": hits, "truncated": True}
    return {"query": query, "hits": hits, "truncated": False}


@mcp.tool()
def cascadeur_batch(requests: list[dict], reload_ops: bool = False) -> dict:
    """Run several bridge ops in ONE Cascadeur session (faster than separate
    calls). Each request: {"op": str, "args": dict}. Discover ops with
    {"op": "ops.list"}. Example: [{"op": "scene.info", "args": {}},
    {"op": "rig.joints", "args": {"limit": 10}}]."""
    try:
        responses = bridge.run_ops(
            [{"op": r.get("op"), "args": r.get("args") or {}} for r in requests],
            reload_ops=reload_ops)
        return {"responses": responses}
    except BridgeError as e:
        return {"error": str(e)}


# ------------------------------------------------------------------ scene


@mcp.tool()
def scene_info() -> dict:
    """Current scene overview: name, path, frames, current frame, object count,
    selection, open tabs."""
    return _call("scene.info")


@mcp.tool()
def scene_manage(action: str, path: str = "", frame: int = 0,
                 frames: int = 0, name: str = "") -> dict:
    """Manage scenes. action: 'new' | 'open' (path: .casc file) | 'save'
    (path optional) | 'close_tab' (name optional, defaults to current) |
    'set_frame' (frame) | 'set_clip_length' (frames)."""
    if action == "new":
        return _call("scene.new")
    if action == "open":
        return _call("scene.open", {"path": path})
    if action == "save":
        return _call("scene.save", {"path": path or None})
    if action == "close_tab":
        return _call("scene.close_tab", {"name": name or None})
    if action == "set_frame":
        return _call("scene.set_frame", {"frame": frame})
    if action == "set_clip_length":
        return _call("scene.set_clip_length", {"frames": frames})
    return {"error": "unknown action %r" % action}


@mcp.tool()
def add_prop(shape: str = "cube", position: list[float] | None = None,
             scale: list[float] | None = None, name: str = "",
             lock: bool = True) -> dict:
    """Add a STATIC set piece (cube/sphere/cylinder/plane) that does NOT animate.
    Position/scale are written across all frames (constant) and the object is
    locked, so it never drifts or gets posed — use for chairs, boxes, floors,
    targets. position/scale are 3-element lists (cube base size ~80 units)."""
    return _call("scene.add_prop", {"shape": shape, "position": position,
                                    "scale": scale, "name": name or None,
                                    "lock": lock})


@mcp.tool()
def add_chair(seat_z: float = 42.0, seat_top_y: float = 45.0, seat_w: float = 40.0,
              seat_d: float = 34.0, back: bool = True) -> dict:
    """Build a simple STATIC chair (seat + 4 legs + optional backrest) at X=0,
    Z=seat_z with the seat surface at Y=seat_top_y. Returns the seat center for
    placing the sit pose. The seat opening faces -Z (backrest at +Z), so a
    character sits facing -Z with its back to the backrest."""
    return _call("scene.add_chair", {"seat_z": seat_z, "seat_top_y": seat_top_y,
                                     "seat_w": seat_w, "seat_d": seat_d,
                                     "back": back})


@mcp.tool()
def import_fbx(path: str, mode: str = "model", new_scene: bool = False) -> dict:
    """Import an FBX file. mode: 'model' (mesh+skeleton), 'scene' (full scene),
    'animation' (onto existing rig), 'animation_to_selected_objects',
    'animation_to_selected_frames', 'model_to_selected'. new_scene=True opens a
    fresh tab first (recommended for a new character)."""
    return _call("fbx.import", {"path": path, "mode": mode, "new_scene": new_scene})


@mcp.tool()
def export_fbx(path: str, what: str = "all", ascii: bool | None = None,
               up_axis: str | None = None, bake_animation: bool | None = None,
               apply_euler_filter: bool | None = None) -> dict:
    """Export to FBX. what: 'all' (all exportable objects), 'model', 'joints'
    (skeleton only), 'selected'. Optional: ascii (True=ASCII FBX), up_axis
    ('X'|'Y'|'Z'), bake_animation, apply_euler_filter."""
    return _call("fbx.export", {
        "path": path, "what": what, "ascii": ascii, "up_axis": up_axis,
        "bake_animation": bake_animation, "apply_euler_filter": apply_euler_filter})


# ------------------------------------------------------------------ objects


@mcp.tool()
def list_objects(name_re: str = "", behaviour: str = "", limit: int = 200,
                 with_behaviours: bool = False) -> dict:
    """List scene objects. name_re: regex filter on names. behaviour: only
    objects with this behaviour (e.g. 'Joint', 'MeshObject', 'RigInfo').
    with_behaviours=True includes each object's behaviour list (slower)."""
    return _call("objects.list", {
        "name_re": name_re or None, "behaviour": behaviour or None,
        "limit": limit, "with_behaviours": with_behaviours})


@mcp.tool()
def get_hierarchy(behaviour: str = "Joint") -> dict:
    """Object parent/child tree. Default restricts to skeleton joints
    (behaviour='Joint'); pass behaviour='' for all objects."""
    return _call("objects.hierarchy", {"behaviour": behaviour or None})


@mcp.tool()
def select_objects(names: list[str] | None = None, name_re: str = "",
                   behaviour: str = "", mode: str = "set") -> dict:
    """Select objects by exact names, regex or behaviour. mode: 'set' | 'add'.
    Empty filters clear the selection."""
    if not names and not name_re and not behaviour:
        return _call("selection.clear")
    return _call("selection.set", {
        "names": names, "name_re": name_re or None,
        "behaviour": behaviour or None, "mode": mode})


@mcp.tool()
def get_selection() -> dict:
    """List currently selected objects."""
    return _call("selection.get")


# ------------------------------------------------------------------ rig


@mcp.tool()
def bone_map() -> dict:
    """Classify the scene skeleton into canonical bone roles regardless of
    naming convention (Mixamo, UE4/UE5, CC3/AccuRig, Daz, custom): hips,
    spine_chain, chest, neck, head, clavicle/upperarm/forearm/hand_[l|r],
    thigh/calf/foot/toe_[l|r], fingers (thumb/index/middle/ring/pinky per
    side). Each role includes the actual joint name, its controller points
    (MainPoint/AdditionalPoint/DirectionPoint...) and world position. ALWAYS
    call this before posing and address bones via the returned names — never
    hardcode a naming convention. Also reveals which fingers have controllers
    (fingers without controllers cannot be animated)."""
    return _call("rig.bone_map")


@mcp.tool()
def rig_info() -> dict:
    """Rig overview: joint count, RigInfo entries, point controllers, boxes.
    Also see get_hierarchy and rig_joints."""
    return _call("rig.info")


@mcp.tool()
def rig_joints(frame: int | None = None, name_re: str = "",
               limit: int = 500) -> dict:
    """Skeleton joints with parent links and world positions at a frame
    (default: current)."""
    return _call("rig.joints", {"frame": frame, "name_re": name_re or None,
                                "limit": limit})


@mcp.tool()
def rig_mode(on: bool, keep_changes: bool = True) -> dict:
    """Enter (on=True) or leave (on=False) rig mode. Leaving regenerates the rig;
    keep_changes=False discards rig-mode edits."""
    return _call("rig.mode", {"on": on, "keep_changes": keep_changes})


@mcp.tool()
def auto_rig(template: str = "Mixamo_Namespace_Template_New",
             autoposing: bool = True) -> dict:
    """Fully automatic character rigging: enter rig mode (creating Rig info over
    all joints), apply a Quick Rig template, generate the rig, and leave rig
    mode. The skeleton must already be imported (see import_fbx). Templates:
    use rig_templates() to list; common ones: 'Mixamo_Namespace_Template_New'
    (mixamorig: prefix), 'Mixamo_No_Namespace_Template_New', 'UE5', 'UE4_New',
    'CC3_char' (AccuRig/Character Creator), 'Metahuman', 'Daz3d_Gen9_...',
    'standard'. Takes ~10-30s."""
    return _call("rig.quick_rig", {"template": template, "autoposing": autoposing})


@mcp.tool()
def rig_templates() -> dict:
    """List available Quick Rig templates (.qrigcasc) bundled with Cascadeur."""
    return _call("rig.qrt_templates")


@mcp.tool()
def quick_rig_tool(action: str = "open") -> dict:
    """Quick Rigging Tool window helpers (manual flow). action: 'open' shows the
    QRT window so the user can map joints by hand; 'introspect' lists the
    tool's scriptable API. For automatic rigging use auto_rig instead."""
    if action == "open":
        return _call("rig.qrt_open")
    return _call("rig.qrt_introspect")


# ------------------------------------------------------------------ transforms


@mcp.tool()
def get_transforms(names: list[str] | None = None, name_re: str = "",
                   behaviour: str = "", frame: int | None = None,
                   limit: int = 100) -> dict:
    """Read object transforms at a frame (default: current): global/local
    position, local rotation/scale, and world position derived from the joint
    matrix. Filter by names, regex or behaviour ('Joint' for the skeleton)."""
    return _call("transform.get", {
        "names": names, "name_re": name_re or None,
        "behaviour": behaviour or None, "frame": frame, "limit": limit})


@mcp.tool()
def set_transforms(items: list[dict], frame: int | None = None,
                   set_key: bool = True, validate: bool = True) -> dict:
    """Move/rotate objects on a frame and run the rig update. items example:
    [{"name": "mixamorig:LeftHand_MainPoint", "global_position": [10,150,20]}].
    Supported per-item keys: global_position, local_position, local_rotation,
    local_scale (3-element lists). set_key=True keys the frame. validate=True
    (default) runs the IK-correctness guard: clamps limb targets to the rig's
    reach and feet to the ground so nothing over-stretches or clips the floor —
    the adjustments are reported."""
    adj = []
    if validate:
        try:
            model = rigmodel.get_model(bridge)
            gp_items = [i for i in items if "global_position" in i]
            other = [i for i in items if "global_position" not in i]
            clamped, adj = rigmodel.clamp_items(gp_items, model)
            items = clamped + other
        except Exception as e:
            adj = [f"(validation skipped: {e})"]
    res = _call("transform.set", {"items": items, "frame": frame,
                                  "set_key": set_key})
    if isinstance(res, dict) and adj:
        res = dict(res) if "result" not in res else res
        res["ik_adjustments"] = adj
    return res


@mcp.tool()
def rig_reach() -> dict:
    """Report the rig model used by the IK-correctness guard: per-limb reach
    (max hand/foot distance from the chain root), controller-point rest
    positions, hips rest height, and ground level. Use these numbers when
    authoring so targets stay within reach."""
    try:
        model = rigmodel.get_model(bridge, force=True)
    except BridgeError as e:
        return {"error": str(e)}
    return {"namespace": model.get("namespace"),
            "chains": model.get("chains"),
            "hips_rest": model.get("hips_rest"),
            "ground_y": model.get("ground_y")}


# ------------------------------------------------------------------ keyframes


@mcp.tool()
def tracks(action: str = "list", name: str = "", object_names: list[str] | None = None,
           with_objects: bool = False) -> dict:
    """Timeline tracks (layers). action: 'list' | 'create' (name) |
    'move_objects' (object_names -> track `name`)."""
    if action == "list":
        return _call("tracks.list", {"with_objects": with_objects})
    if action == "create":
        return _call("tracks.create", {"name": name})
    if action == "move_objects":
        return _call("tracks.move_objects", {"object_names": object_names or [],
                                             "track_name": name})
    return {"error": "unknown action %r" % action}


@mcp.tool()
def keyframes(action: str, frames: list[int] | None = None,
              track_names: list[str] | None = None,
              object_names: list[str] | None = None,
              start: int = 0, end: int | None = None) -> dict:
    """Keyframe operations on tracks (select tracks by track_names or by
    object_names; neither = all tracks).
    action: 'list' (keys with interpolation/IK-FK per track in [start, end)),
    'set' (create keys at frames), 'delete' (remove keys at frames)."""
    sel = {"track_names": track_names, "object_names": object_names}
    if action == "list":
        return _call("keys.list", dict(sel, start=start, end=end))
    if action == "set":
        return _call("keys.set", dict(sel, frames=frames or []))
    if action == "delete":
        return _call("keys.delete", dict(sel, frames=frames or []))
    return {"error": "unknown action %r" % action}


@mcp.tool()
def set_interval(frame: int, interpolation: str = "",
                 ik_fk: str = "", fixation: str = "", on_key: bool = False,
                 track_names: list[str] | None = None,
                 object_names: list[str] | None = None) -> dict:
    """Set properties of the timeline section containing `frame`.
    interpolation: BEZIER | LOW_AMPLITUDE_BEZIER | LINEAR | STEP | FIXED |
    CLAMPED_BEZIER | NONE. ik_fk: 'IK' | 'FK'. fixation: 'free' | 'fulcrum'.
    on_key=True applies ik_fk/fixation to the keyframe instead of the interval."""
    return _call("interval.set", {
        "frame": frame, "interpolation": interpolation or None,
        "ik_fk": ik_fk or None, "fixation": fixation or None, "on_key": on_key,
        "track_names": track_names, "object_names": object_names})


@mcp.tool()
def export_animation(path: str, format: str = "fbx", frame_start: int = 0,
                     frame_end: int | None = None) -> dict:
    """Export baked skeletal animation WITHOUT the paid Cascadeur FBX export:
    bakes joint transforms per frame over the bridge and writes the file
    locally. format: 'fbx' (ASCII FBX 7.3, skeleton+animation curves — drop it
    next to the original character FBX in Unity/Blender and the clip retargets
    by joint names, classic Mixamo workflow), 'bvh', or 'json' (raw bake data).
    No mesh is included (mesh export requires a paid license)."""
    try:
        bake, _ = bridge.run_op("anim.bake", {"frame_start": frame_start,
                                              "frame_end": frame_end})
    except BridgeError as e:
        return {"error": str(e)}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    from . import fbx_writer
    if format == "fbx":
        fbx_writer.write_fbx_ascii(bake, path)
    elif format == "bvh":
        fbx_writer.write_bvh(bake, path)
    elif format == "json":
        with open(path, "w", encoding="utf-8") as f:
            json.dump(bake, f)
    else:
        return {"error": "format must be fbx | bvh | json"}
    return {"exported": path, "format": format, "joints": bake["joint_count"],
            "frames": bake["frame_count"], "size": os.path.getsize(path)}


@mcp.tool()
def apply_local_transforms(joints: list[dict], frame: int | None = None) -> dict:
    """Set FULL local transforms (position + rotation + scale) per joint — the
    CORRECT way to transfer a pose so every bone keeps its orientation, instead
    of driving a few IK point positions (which lets IK guess and twist the
    legs/arms). joints: [{"name": <joint>, "local_position":[x,y,z],
    "local_rotation":[rx,ry,rz] euler DEGREES, "local_scale":[sx,sy,sz]}] (any
    subset). Matches by joint-name suffix (namespace-agnostic) and switches the
    tracks to FK so the transforms are respected. Get the values from anim.bake
    of a source frame. This is the foundation for clean, no-twist retargeting."""
    return _call("anim.apply_local", {"joints": joints, "frame": frame})


@mcp.tool()
def transfer_pose(source_casc: str, source_frame: int,
                  target_frame: int = 0) -> dict:
    """Copy ONE pose (all bones, full loc+rot) from a source .casc frame onto the
    current character via apply_local_transforms — correct orientation, no
    twisting. Bakes source_frame from source_casc, then applies it at
    target_frame on the current scene."""
    try:
        with bridge.session():
            bridge.run_op("scene.open", {"path": source_casc, "new_tab": True})
            bake, _ = bridge.run_op("anim.bake", {"frame_start": source_frame,
                                                 "frame_end": source_frame + 1})
        joints = [{"name": j["name"],
                   "local_position": j["frames"][0][:3],
                   "local_rotation": j["frames"][0][3:6]} for j in bake["joints"]]
        return _call("anim.apply_local", {"joints": joints, "frame": target_frame})
    except BridgeError as e:
        return {"error": str(e)}


@mcp.tool()
def auto_pose_update() -> dict:
    """Run Cascadeur's ML AutoPosing on the current frame: after you move a few
    main controller points, this adjusts the remaining points to a natural
    pose. Check the result with viewport_screenshot."""
    return _call("ai.auto_pose_update")


@mcp.tool()
def block_pose(controllers: list[dict], frame: int, autopose: bool = False,
               ik_fk: str = "", track_names: list[str] | None = None,
               object_names: list[str] | None = None) -> dict:
    """Block ONE key pose the proper Cascadeur way (Drafting stage): set only the
    FEW defining controller points and key the frame. The neural rig's
    AutoPosingLinks complete the rest of the body AUTOMATICALLY when you move
    controllers — so you do NOT need to place every point. controllers:
    [{"name": "<ns>Hips_MainPoint", "global_position": [x,y,z]}, ...] —
    typically feet (contacts) + hips + intent (a reaching hand). autopose=True
    additionally runs the explicit ai.auto_pose_update ML refine (leave False:
    it's redundant with the automatic autoposing and less stable headless).
    ik_fk ('IK'|'FK'|'GR') optionally set on the keyframe (IK for contacts).
    Set fewer controllers than you think — the rig fills knees, spine,
    shoulders, unmoved limbs."""
    reqs = [{"op": "scene.set_frame", "args": {"frame": frame}},
            {"op": "transform.set",
             "args": {"items": controllers, "frame": frame, "set_key": True}}]
    if autopose:
        reqs.append({"op": "ai.auto_pose_update", "args": {}})
    if ik_fk:
        reqs.append({"op": "interval.set",
                     "args": {"frame": frame, "ik_fk": ik_fk, "on_key": True,
                              "track_names": track_names,
                              "object_names": object_names}})
    try:
        resps = bridge.run_ops(reqs)
    except BridgeError as e:
        return {"error": str(e)}
    setr = next((r for r in resps if r.get("id") == 1), resps[1] if len(resps) > 1 else {})
    return {"frame": frame,
            "applied": (setr.get("result") or {}).get("applied"),
            "autoposed": autopose,
            "errors": [r.get("error") for r in resps if r.get("status") != "ok"]}


@mcp.tool()
def animate_sequence(poses: list[dict], interpolation: str = "BEZIER",
                     fulcrum_feet: bool = True, autopose: bool = False,
                     out_fbx: str = "", save_casc: str = "") -> dict:
    """Orchestrate a full blocking->spline pass the proper Cascadeur way. `poses`
    is an ordered list of SPARSE key poses (few controllers each — the rig
    autoposes the rest):
      [{"frame": int, "controllers": [{"name","global_position"}...],
        "ik_fk": "IK"|"FK"|"GR" (optional),
        "fulcrum": ["<ns>LeftFoot_MainPoint", ...] (optional planted feet)}]
    Algorithm (Drafting + Spline stages): set clip length; for each pose set its
    few controllers + key (the rig's AutoPosingLinks auto-complete the body);
    mark fulcrum on planted feet; spline every interval. autopose=True adds the
    explicit ML refine per pose (slower + less stable headless; usually leave
    False). Then optionally export FBX / save .casc. Keep controllers sparse
    (feet+hips+intent)."""
    if not poses:
        return {"error": "no poses given"}
    frames = sorted(p["frame"] for p in poses)
    reqs = [{"op": "scene.set_clip_length", "args": {"frames": frames[-1] + 1}},
            {"op": "keys.set", "args": {"frames": [frames[0]]}}]
    try:
      with bridge.session():   # one trigger for the whole build
        bridge.run_ops(reqs)
        blocked = []
        for p in sorted(poses, key=lambda q: q["frame"]):
            f = p["frame"]
            b = [{"op": "scene.set_frame", "args": {"frame": f}},
                 {"op": "transform.set",
                  "args": {"items": p["controllers"], "frame": f, "set_key": True}}]
            if autopose:
                b.append({"op": "ai.auto_pose_update", "args": {}})
            if p.get("ik_fk"):
                b.append({"op": "interval.set",
                          "args": {"frame": f, "ik_fk": p["ik_fk"], "on_key": True}})
            rs = bridge.run_ops(b)
            blocked.append({"frame": f,
                            "ok": all(r.get("status") == "ok" for r in rs)})
        # fulcrum on planted feet
        if fulcrum_feet:
            ful = []
            for p in poses:
                for pt in p.get("fulcrum", []):
                    ful.append({"op": "interval.set",
                                "args": {"frame": p["frame"], "fixation": "fulcrum",
                                         "on_key": True, "object_names": [pt]}})
            for i in range(0, len(ful), 6):
                bridge.run_ops(ful[i:i + 6])
        # spline every interval
        spline = [{"op": "interval.set",
                   "args": {"frame": frames[k], "interpolation": interpolation}}
                  for k in range(len(frames) - 1)]
        for i in range(0, len(spline), 6):
            bridge.run_ops(spline[i:i + 6])
        result = {"poses_blocked": blocked, "interpolation": interpolation}
        if save_casc:
            bridge.run_op("scene.save", {"path": save_casc})
            result["casc"] = save_casc
        if out_fbx:
            bake, _ = bridge.run_op("anim.bake")
            from . import fbx_writer
            os.makedirs(os.path.dirname(out_fbx) or ".", exist_ok=True)
            fbx_writer.write_fbx_ascii(bake, out_fbx)
            result["fbx"] = out_fbx
    except BridgeError as e:
        return {"error": str(e)}
    return result


@mcp.tool()
def quick_animate(mocap_fbx: str, character_casc: str = "",
                  out_fbx: str = "", save_casc: str = "") -> dict:
    """One-command retarget pipeline (minimal bridge sessions for speed):
    optionally open a pre-rigged character (.casc), natively import the mocap
    animation onto it, optionally export a baked FBX and/or save a .casc.
    Timing (measured): retarget onto an already-open rigged char ~5-10s; opening
    an 86MB .casc ~5-10s; our FBX bake ~16s (free-license tax; skip out_fbx if
    not needed). Pre-rig characters ONCE and reuse to skip auto_rig (15-46s)."""
    import time as _t
    t0 = _t.monotonic()
    reqs = []
    if character_casc:
        reqs.append({"op": "scene.open",
                     "args": {"path": character_casc, "new_tab": True}})
    reqs.append({"op": "fbx.import",
                 "args": {"path": mocap_fbx, "mode": "animation"}})
    if save_casc:
        reqs.append({"op": "scene.save", "args": {"path": save_casc}})
    try:
        bridge.run_ops(reqs)
        result = {"retargeted": mocap_fbx, "elapsed_sec": None}
        if out_fbx:
            bake, _ = bridge.run_op("anim.bake")
            from . import fbx_writer
            os.makedirs(os.path.dirname(out_fbx) or ".", exist_ok=True)
            fbx_writer.write_fbx_ascii(bake, out_fbx)
            result["fbx"] = out_fbx
            result["frames"] = bake["frame_count"]
    except BridgeError as e:
        return {"error": str(e)}
    result["elapsed_sec"] = round(_t.monotonic() - t0, 1)
    if save_casc:
        result["casc"] = save_casc
    return result


@mcp.tool()
def retarget_animation(fbx_path: str, mode: str = "animation") -> dict:
    """Cleanly retarget a whole animation FBX onto the CURRENT rigged character
    using Cascadeur's native importer (maps full joint transforms — position AND
    rotation — by joint name). This is the correct way to transfer motion when
    the reference and target share a skeleton naming (both Mixamo/UE/etc.);
    orientation is preserved (no twist). mode: 'animation' (whole skeleton) or
    'animation_to_selected_objects'. For cross-skeleton or single-pose transfer
    where names differ, use the dataset tools (pose_apply) instead. After
    retargeting, add forward travel with a root-translation pass if the source
    is in-place."""
    return _call("fbx.import", {"path": fbx_path, "mode": mode})


@mcp.tool()
def dataset_capture(name: str, frame_start: int = 0,
                    frame_end: int | None = None) -> dict:
    """Capture the CURRENT scene's animation into the reference-motion dataset
    (dataset/<name>.json): per-joint world positions + local euler rotations per
    frame, foot contacts, hip height, detected contact/toe-off key frames.
    Workflow: import a reference FBX (import_fbx mode='scene'), then call this.
    Build a library of walk/run/jump/idle clips to pose limbs from real data."""
    try:
        record, _ = bridge.run_op("anim.capture", {"frame_start": frame_start,
                                                   "frame_end": frame_end})
    except BridgeError as e:
        return {"error": str(e)}
    src = "current scene"
    try:
        info, _ = bridge.run_op("scene.info")
        src = info.get("name", src)
    except Exception:
        pass
    return dataset.save_capture(name, src, record)


@mcp.tool()
def dataset_list() -> dict:
    """List reference-motion clips in the dataset with frame counts, hip height,
    and detected key frames (contacts/toe-offs). Use clip names with pose_apply
    / motion_retarget."""
    return {"clips": dataset.list_clips(), "dir": dataset.DATASET_DIR}


@mcp.tool()
def dataset_pose(clip: str, ref_frame: int) -> dict:
    """Inspect one reference frame: the world positions the target rig points
    would be driven to (per bone role). Read this to understand how a real pose
    places arms/legs before applying it."""
    try:
        rec = dataset.load(clip)
    except Exception as e:
        return {"error": str(e)}
    joints = rec["joints"]
    r2j = rec.get("role_to_joint", {})
    out = {}
    for role in dataset.APPLY_ROLES:
        jn = r2j.get(role)
        j = joints.get(jn) if jn else None
        if j:
            fr = min(ref_frame, len(j["world"]) - 1)
            out[role] = {"joint": jn, "world": j["world"][fr],
                         "local_rot": j["local_rot"][fr]}
    return {"clip": clip, "frame": ref_frame, "hip_height": rec.get("hip_height"),
            "roles": out}


@mcp.tool()
def pose_apply(clip: str, ref_frame: int, target_frame: int | None = None,
               roles: list[str] | None = None, set_key: bool = True,
               orient: bool = True) -> dict:
    """Apply a reference clip's pose onto the current character's rig points,
    placing arms/legs from real data. clip/ref_frame from dataset_list. roles:
    limit to canonical roles (e.g. ['upperarm_l','forearm_l','hand_l']) to
    borrow just an arm. target_frame defaults to the current frame. orient=True
    also transfers segment orientation/twist via the rig's helper points (fixes
    'floating' limbs); set False for position-only."""
    try:
        rec = dataset.load(clip)
    except Exception as e:
        return {"error": str(e)}
    try:
        bm, _ = bridge.run_op("rig.bone_map")
        hg = None
        if orient:
            hg, _ = bridge.run_op("rig.helper_geometry")
    except BridgeError as e:
        return {"error": str(e)}
    items = dataset.pose_items(rec, ref_frame, bm, roles, helper_geometry=hg)
    if not items:
        return {"error": "no matching rig points; is the character rigged?"}
    return _call("transform.set", {"items": items, "frame": target_frame,
                                   "set_key": set_key})


@mcp.tool()
def motion_retarget(clip: str, target_start: int = 0, ref_start: int = 0,
                    ref_end: int | None = None, step: int = 1) -> dict:
    """Retarget a whole reference clip onto the current rigged character: for
    each reference frame, drive the rig points to the (hip-scaled) reference
    joint world positions and key it. Reproduces the reference motion on your
    character via IK. Sets clip length and BEZIER. Reference and target should
    be the same skeleton family (both Mixamo etc.)."""
    try:
        rec = dataset.load(clip)
    except Exception as e:
        return {"error": str(e)}
    try:
        bm, _ = bridge.run_op("rig.bone_map")
    except BridgeError as e:
        return {"error": str(e)}
    n = rec["frame_count"]
    ref_end = n if ref_end is None else min(ref_end, n)
    ref_frames = list(range(ref_start, ref_end, max(1, step)))
    target_frames = [target_start + i for i in range(len(ref_frames))]

    requests = [{"op": "scene.set_clip_length",
                 "args": {"frames": target_frames[-1] + 1}}]
    for rf, tf in zip(ref_frames, target_frames):
        items = dataset.pose_items(rec, rf, bm)
        requests.append({"op": "transform.set",
                         "args": {"items": items, "frame": tf, "set_key": True}})
    try:
      with bridge.session():   # one trigger for the whole retarget
        applied = 0
        CH = 6
        for i in range(0, len(requests), CH):
            resps = bridge.run_ops(requests[i:i + CH])
            applied += sum(1 for r in resps if r.get("status") == "ok")
        # spline
        bridge.run_ops([{"op": "interval.set",
                         "args": {"frame": tf, "interpolation": "BEZIER"}}
                        for tf in target_frames[:-1]])
    except BridgeError as e:
        return {"error": str(e)}
    return {"clip": clip, "frames_retargeted": len(target_frames),
            "target_range": [target_frames[0], target_frames[-1]],
            "ops_ok": applied}


@mcp.tool()
def root_motion(frame_start: int = 0, frame_end: int | None = None) -> dict:
    """Run Cascadeur's generative Root Motion over an interval (needs >=2
    keyframes). Extracts the world trajectory from an in-place animation and
    drives the character root through space based on foot contacts. Works on
    the free license. After running, re-check foot planting and export."""
    return _call("ai.root_motion", {"frame_start": frame_start,
                                    "frame_end": frame_end})


# ------------------------------------------------------------------ tools


@mcp.tool()
def cascadeur_action(name: str) -> dict:
    """Call a named application action by its official action id (see the
    Cascadeur docs action-id list), e.g. 'Scene.Undo', 'Scene.Redo',
    'Timeline.Change to IK key', 'AutoPosingTool.Update',
    'MirrorTool.Mirror on current frame'. Set the timeline selection / current
    frame first when the action needs it."""
    return _call("tool.action", {"name": name})


@mcp.tool()
def set_kinematics(mode: str, frame: int, on_interval: bool = False) -> dict:
    """Set IK / FK / GR kinematics on the current keyframe (or the interval).
    mode: 'IK' (default; positions fixed in world — use for contacts: planted
    feet, grasping hands), 'FK' (local rotation from parent — free rotational
    limb swings), 'GR' (global-rotation, arch interpolation for limbs). Uses the
    official Timeline.Change-to-*-key actions. Select the tracks/objects first
    if you want it per-limb; otherwise it applies to the current selection."""
    m = mode.upper()
    if m not in ("IK", "FK", "GR"):
        return {"error": "mode must be IK, FK or GR"}
    _call("scene.set_frame", {"frame": frame})
    return _call("tool.action", {"name": f"Timeline.Change to {m} key"})


@mcp.tool()
def foot_lock(foot_points: list[str], frame_start: int, frame_end: int) -> dict:
    """Procedural de-slide: freeze each foot controller's world XZ across the
    planted interval [frame_start, frame_end] so it doesn't drift (our
    substitute for AutoPhysics fulcrum cleaning). foot_points: e.g.
    ['mixamorig:LeftFoot_MainPoint']. Reads current positions, re-keys them
    locked. Mark the interval fulcrum too for best results."""
    frames = list(range(int(frame_start), int(frame_end) + 1))
    fixed = 0
    try:
        for pt in foot_points:
            # read world pos over the interval
            world = {}
            for f in frames:
                r, _ = bridge.run_op("transform.get",
                                     {"names": [pt.split(":")[-1]], "frame": f})
                # match by full name
                tr = next((t for t in r.get("transforms", [])
                           if t["name"] == pt or t["name"].endswith(pt.split(":")[-1])), None)
                if tr and ("position" in tr or "global_position" in tr):
                    world[f] = tr.get("position") or tr["global_position"]
            if len(world) < 2:
                continue
            locked = physics.foot_lock_positions(world, [f for f in frames if f in world])
            items = [{"name": pt, "global_position": locked[f]} for f in locked]
            for f, itm in zip(sorted(locked), items):
                bridge.run_ops([{"op": "transform.set",
                                 "args": {"items": [itm], "frame": f, "set_key": True}}])
                fixed += 1
    except BridgeError as e:
        return {"error": str(e)}
    return {"foot_points": foot_points, "frames": frames, "keys_locked": fixed}


@mcp.tool()
def add_jump_arc(hips_point: str, launch_frame: int, land_frame: int,
                 launch_pos: list[float] | None = None,
                 land_pos: list[float] | None = None) -> dict:
    """Procedural ballistic trajectory: drive the hips/root through a gravity
    parabola over the airborne interval [launch_frame, land_frame] (our
    substitute for the Pro AutoPhysics ballistic tool). If launch_pos/land_pos
    are omitted, the current hips world positions at those frames are used. Keys
    every airborne frame; returns the apex frame (extend legs there)."""
    try:
        jn = hips_point.split(":")[-1]
        if launch_pos is None:
            r, _ = bridge.run_op("transform.get", {"names": [jn], "frame": launch_frame})
            launch_pos = (r["transforms"][0].get("position")
                          or r["transforms"][0]["global_position"])
        if land_pos is None:
            r, _ = bridge.run_op("transform.get", {"names": [jn], "frame": land_frame})
            land_pos = (r["transforms"][0].get("position")
                        or r["transforms"][0]["global_position"])
    except (BridgeError, Exception) as e:
        return {"error": f"could not read hips: {e}"}
    n = int(land_frame) - int(launch_frame) + 1
    arc = physics.ballistic_arc(launch_pos, land_pos, n)
    apex = int(launch_frame) + physics.apex_frame(launch_pos, land_pos, n)
    try:
        for i, pos in enumerate(arc):
            f = int(launch_frame) + i
            bridge.run_ops([{"op": "transform.set",
                             "args": {"items": [{"name": hips_point,
                                                 "global_position": pos}],
                                      "frame": f, "set_key": True}}])
    except BridgeError as e:
        return {"error": str(e)}
    return {"airborne_frames": [int(launch_frame), int(land_frame)],
            "apex_frame": apex, "peak_height": max(p[1] for p in arc)}


@mcp.tool()
def add_secondary_motion(point: str, frame_start: int, frame_end: int,
                         lag_frames: int = 3, overshoot: float = 0.35) -> dict:
    """Procedural overlap/follow-through: make a trailing part (hand, head, prop)
    lag its own motion with a damped overshoot over [frame_start, frame_end] —
    our substitute for AutoPhysics secondary motion. Reads the point's current
    trajectory, applies lag+overshoot, re-keys it."""
    frames = list(range(int(frame_start), int(frame_end) + 1))
    jn = point.split(":")[-1]
    try:
        traj = []
        for f in frames:
            r, _ = bridge.run_op("transform.get", {"names": [jn], "frame": f})
            tr = next((t for t in r.get("transforms", []) if t["name"].endswith(jn)), None)
            traj.append(tr.get("position") or tr["global_position"])
        new = physics.secondary_motion(traj, lag_frames, overshoot)
        for f, pos in zip(frames, new):
            bridge.run_ops([{"op": "transform.set",
                             "args": {"items": [{"name": point, "global_position": pos}],
                                      "frame": f, "set_key": True}}])
    except (BridgeError, Exception) as e:
        return {"error": str(e)}
    return {"point": point, "frames": frames, "lag": lag_frames}


@mcp.tool()
def health_check() -> dict:
    """Diagnose the pipeline: is Cascadeur running, does the bridge connect,
    latency, current scene. Use before a long build; if not running it will be
    relaunched by the next call (crash recovery is built in)."""
    running = bridge.is_running()
    try:
        info, _ = bridge.run_op("scene.info")
        return {"cascadeur_running": running, "bridge_ok": True,
                "latency_sec": round(bridge.last_latency or -1, 2),
                "scene": info.get("name"), "frames": info.get("animation_frames")}
    except Exception as e:
        return {"cascadeur_running": running, "bridge_ok": False, "error": str(e)}


@mcp.tool()
def physics_snap(select_all_points: bool = True) -> dict:
    """Apply Cascadeur's AutoPhysics ('Snap to Auto Physics') to make the
    selected motion physically accurate (balance via center of mass, ballistic
    arcs, secondary/compensation motion). CAVEAT: on the FREE license AutoPhysics
    is LIMITED to floor interactions (verified: runs 'Autophysics core finished'
    with no upgrade dialog, but produced no change on a quasi-static sit) and is
    CRASH-PRONE headless. Save a .casc first. Best on dynamic motion (jumps,
    runs) and with a Pro license. select_all_points selects the rig point
    controllers before applying."""
    reqs = []
    if select_all_points:
        reqs.append({"op": "python.exec", "args": {"code":
            "import csc\n"
            "mv=scene.model_viewer(); bv=mv.behaviour_viewer()\n"
            "ids=set(bv.get_behaviour_owner(b) for b in bv.get_behaviours('Point'))\n"
            "try: scene.selector().select(ids, csc.domain.SelectorMode.NewSelection)\n"
            "except Exception: scene.selector().select(ids)\n"
            "result={'selected':len(ids)}"}})
    reqs.append({"op": "tool.action",
                 "args": {"name": "AutoPhysicsTool.Snap to Auto Physics"}})
    try:
        bridge.run_ops(reqs)
    except BridgeError as e:
        return {"error": str(e)}
    return {"physics": "snap applied (verify; free-license = floor-only, may be "
            "a no-op on static motion)"}


@mcp.tool()
def ballistic_trajectory() -> dict:
    """Add a ballistic (physics) trajectory over the selected interval for a
    jump/fall/throw so the airborne arc follows gravity ('Add ballistic
    trajectory'). Select the character points and the airborne interval first.
    Free-license/headless: runs but limited and crash-prone — save first."""
    return _call("tool.action",
                 {"name": "BallisticTrajectoryTool.Add ballistic trajectory"})


@mcp.tool()
def mirror(what: str = "frame", object_names: list[str] | None = None) -> dict:
    """Mirror pose on the current frame ('frame') or the selected interval
    ('interval') for named objects (default: current selection)."""
    return _call("tool.mirror", {"what": what, "object_names": object_names})


@mcp.tool()
def set_camera(preset: str = "3q", target: list[float] | None = None,
               distance: float = 220.0) -> dict:
    """Aim the viewport camera before rendering. preset: 'side_l'/'side_r'
    (best for reviewing walk/sit profiles), 'front', 'back', 'top', '3q'
    (three-quarter). target: world point to look at (default character
    mid-height). Call before viewport_screenshot / the GIF render loop."""
    return _call("tool.set_camera", {"preset": preset, "target": target,
                                     "distance": distance})


@mcp.tool()
def viewport_screenshot(width: int = 960, height: int = 540, samples: int = 4):
    """Render the Cascadeur viewport to an image and return it."""
    out_path = os.path.join(os.environ.get("TEMP", "."),
                            "cascadeur_mcp_shot_%d.png" % int(time.time()))
    result = _call("tool.screenshot", {"path": out_path, "width": width,
                                       "height": height, "samples": samples})
    if isinstance(result, dict) and result.get("error"):
        return result
    deadline = time.time() + 20
    while time.time() < deadline:
        if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
            time.sleep(0.3)  # let the writer finish
            with open(out_path, "rb") as f:
                data = f.read()
            try:
                os.remove(out_path)
            except OSError:
                pass
            return Image(data=data, format="png")
        time.sleep(0.5)
    return {"error": "render did not produce a file in 20s", "detail": result}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
