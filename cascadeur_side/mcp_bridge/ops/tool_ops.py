"""Application actions (undo/redo etc.), mirror tool, viewport screenshot."""

from . import resolve_objects


def action_call(ctx, name):
    ctx.app.get_action_manager().call_action(name)
    return {"called": name}


def undo(ctx):
    return action_call(ctx, "Scene.Undo")


def redo(ctx):
    return action_call(ctx, "Scene.Redo")


def mirror(ctx, what="frame", object_names=None):
    """Mirror current frame (or interval) for selected or named objects."""
    tm = ctx.app.get_tools_manager()
    mirror_tool = tm.get_tool("MirrorTool").editor(ctx.app_scene())
    core = mirror_tool.core()
    if object_names:
        ids = set(resolve_objects(ctx, names=object_names))
    else:
        ids = set()
        for i in ctx.scene.selector().selected().ids:
            ids.add(i)
    if what == "frame":
        core.mirror_frame(ids)
    elif what == "interval":
        core.mirror_interval(ids)
    else:
        raise ValueError("what must be 'frame' or 'interval'")
    return {"mirrored": what, "objects": len(ids)}


def _render_params(ctx, width, height, samples):
    params = ctx.csc.tools.RenderParameters()
    params.width = int(width)
    params.height = int(height)
    params.samples = int(samples)
    return params


def screenshot(ctx, path, width=960, height=540, samples=4):
    """Render the viewport to an image file using the RenderToFile tool."""
    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tool = ctx.app.get_tools_manager().get_tool("RenderToFile")
    tool.take_image(ctx.app_scene(), _render_params(ctx, width, height, samples),
                    path.replace("\\", "/"))
    return {"path": path, "exists": os.path.isfile(path),
            "note": "render may complete asynchronously"}


def render_video(ctx, path, width=1280, height=720, samples=4):
    """DANGER: play_to_video_file makes Cascadeur QUIT (observed on the free
    license, 2026.1.3) — do not call this; render a PNG sequence with
    tool.screenshot per frame instead and assemble the video externally."""
    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tool = ctx.app.get_tools_manager().get_tool("RenderToFile")
    tool.play_to_video_file(ctx.app_scene(),
                            _render_params(ctx, width, height, samples),
                            path.replace("\\", "/"))
    return {"path": path, "note": "video records asynchronously while playing"}


def screenshot_clipboard(ctx):
    """Copy the current viewport image to the system clipboard."""
    ctx.app.get_scene_clipboard().copy_image_to_clipboard(ctx.app_scene())
    return {"copied": True}


def set_camera(ctx, preset="3q", target=None, distance=220.0):
    """Aim the active viewport camera. preset: front|back|side_l|side_r|top|3q.
    target: world point to look at (default character mid-height at origin)."""
    import numpy as np
    csc = ctx.csc
    app_scene = ctx.app_scene()
    tgt = target or [0.0, 90.0, 20.0]
    d = float(distance)
    presets = {
        "front":  [tgt[0], tgt[1], tgt[2] - d],
        "back":   [tgt[0], tgt[1], tgt[2] + d],
        "side_l": [tgt[0] + d, tgt[1], tgt[2]],
        "side_r": [tgt[0] - d, tgt[1], tgt[2]],
        "top":    [tgt[0], tgt[1] + d, tgt[2] + 0.1],
        "3q":     [tgt[0] + d * 0.7, tgt[1] + d * 0.35, tgt[2] - d * 0.7],
    }
    if preset not in presets:
        raise ValueError("preset must be one of %s" % sorted(presets))
    pos = presets[preset]

    try:
        vp = app_scene.active_viewport().domain_viewport()
    except Exception:
        vps = app_scene.view_ports()
        vp = vps[0].domain_viewport()
    struct = vp.camera_struct()
    struct.target = np.array([float(tgt[0]), float(tgt[1]), float(tgt[2])],
                             dtype=np.float32)
    struct.position = np.array([float(pos[0]), float(pos[1]), float(pos[2])],
                               dtype=np.float32)
    try:
        struct.type = csc.view.CameraType.PERSPECTIVE
    except Exception:
        pass
    vp.set_camera_struct(struct)
    return {"preset": preset, "target": tgt, "position": pos}


def tool_introspect(ctx, name):
    """Debug helper: list attributes of a tool and its editor."""
    tm = ctx.app.get_tools_manager()
    tool = tm.get_tool(name)
    info = {"tool": [a for a in dir(tool) if not a.startswith("_")]}
    try:
        editor = tool.editor(ctx.app_scene())
        info["editor"] = [a for a in dir(editor) if not a.startswith("_")]
    except Exception as e:
        info["editor_error"] = repr(e)
    return info


OPS = {
    "tool.action": action_call,
    "tool.undo": undo,
    "tool.redo": redo,
    "tool.mirror": mirror,
    "tool.screenshot": screenshot,
    "tool.set_camera": set_camera,
    "tool.render_video": render_video,
    "tool.screenshot_clipboard": screenshot_clipboard,
    "tool.introspect": tool_introspect,
}
