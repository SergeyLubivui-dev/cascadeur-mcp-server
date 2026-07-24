"""Cascadeur's built-in AI/physics tools that run LOCALLY (not the license-gated
ML inbetweening): the physics attractor ("tween machine") and the Editable
Animation / AutoInterpolation pass (the official pipeline's "spline" step).
"""

from . import resolve_objects


_ATTRACT_MODES = ("Previous", "Next", "Inertial", "InverseInertial",
                  "Average", "Interpolation")


def physics_tween(ctx, frame=None, mode="Inertial", factor=1.0,
                  only_key_frames=False, joints_only=False):
    """Physics "tween machine" (AttractorTool): attracts the selected rig points
    toward a physically-plausible pose using the scene's gravity — the LOCAL
    physics in-between that works on the free license (the ML Inbetweening does
    not). mode picks the physics model:
      Inertial        - ballistic continuation of the previous motion (a body
                        in free fall / follow-through). The default.
      InverseInertial - same, extrapolated backwards from the next key.
      Previous/Next   - pulled toward the previous / next key's dynamics.
      Average         - even spacing between neighbouring keys.
      Interpolation   - physics-corrected interpolation between keys.
    factor (0..1) is the strength. Operates on the current frame (or `frame`).
    Great for adding physically-correct arcs/settle to a blocked pose without
    hand-keying every point.
    """
    csc = ctx.csc
    app = ctx.app
    app_scene = ctx.app_scene()   # csc.view.Scene (has gravity_per_frame)
    scene = ctx.scene             # domain scene
    bv = ctx.bv()
    if mode not in _ATTRACT_MODES:
        return {"error": "mode must be one of %s" % (_ATTRACT_MODES,)}
    if frame is not None:
        scene.set_current_frame(int(frame))

    tool = app.get_tools_manager().get_tool("AttractorTool").editor(app_scene)
    settings = tool.get_general_settings()
    settings.factor = float(factor)
    mode_enum = getattr(csc.tools.attractor.ArgsMode, mode)
    args = csc.tools.attractor.Args(scene, app_scene.gravity_per_frame(),
                                    settings, bool(only_key_frames), mode_enum)

    # select the points to attract (all rig Points, or joints if asked)
    points = set()
    try:
        for bh in bv.get_behaviours("Point"):
            points.add(bv.get_behaviour_owner(bh))
    except Exception:
        pass
    if not points:
        return {"error": "no rig Points found to attract (is a character rigged "
                         "and in animation mode?)"}
    scene.selector().select(points, csc.model.ObjectId.null())
    csc.tools.attractor.attract(args)
    return {"tweened": True, "mode": mode, "factor": float(factor),
            "points": len(points), "frame": scene.get_current_frame()}


def auto_interpolate(ctx, frame_start=0, frame_end=None, select_all_layers=True):
    """Editable Animation / AutoInterpolation (ml.editable_animation) — the
    official pipeline's SPLINE step. Takes a dense/baked animation (e.g. the
    per-frame output of a retarget/apply_animation) and adaptively reduces it to
    sparse, EDITABLE keyframes, choosing the best interpolation (Bezier vs
    Clamped) and IK/FK/GR per section and respecting fulcrum/foot contacts.
    Runs locally (not the gated ML). Needs exactly one rigged character in the
    scene. Selects all rig layers across [frame_start, frame_end] first (so the
    "some child layers aren't selected" dialog never blocks) and runs the pass.
    """
    csc = ctx.csc
    scene = ctx.scene
    lv = ctx.lv()
    dv = ctx.dv()
    if frame_end is None:
        frame_end = dv.get_animation_size() - 1
    frame_start, frame_end = int(frame_start), int(frame_end)

    # precondition: exactly one character, else editable_animation pops a modal
    # dialog (which would block Cascadeur headlessly). Fail cleanly instead.
    bv = ctx.bv()
    try:
        rig_infos = bv.get_behaviours("RigInfo")
        n_rigs = len(rig_infos)
    except Exception:
        n_rigs = -1
    if n_rigs == 0:
        return {"error": "no RigInfo in scene — auto_interpolate needs a rigged "
                         "character"}
    if n_rigs > 1:
        return {"error": "%d characters in scene — select exactly one before "
                         "auto_interpolate" % n_rigs}

    if select_all_layers:
        all_ids = list(lv.all_layer_ids())
        sel = scene.get_layers_selector()
        try:
            sel.set_full_selection_by_parts(all_ids, frame_start, frame_end)
        except Exception as e:
            return {"error": "could not select layers: %r" % e}

    import importlib
    import ml.editable_animation as ea
    importlib.reload(ea)  # cheap; keeps up with Cascadeur updates
    try:
        ea.run(scene)
    except ValueError as e:
        return {"error": "editable_animation: %s" % e}
    return {"editable_animation": "done", "interval": [frame_start, frame_end]}


def auto_physics(ctx, on=False):
    """Toggle the AutoPhysicsTool. on=False turns it off and releases all fulcrum
    points (mirrors rig_mode's teardown). AutoPhysics continuously corrects the
    pose toward physical plausibility while you move controllers."""
    app = ctx.app
    editor = app.get_tools_manager().get_tool("AutoPhysicsTool").editor(
        app.current_scene())
    if on:
        # best-effort: the editor exposes turn_off; turn_on may be named
        # differently across builds — try a couple of spellings.
        for name in ("turn_on", "set_on", "enable"):
            fn = getattr(editor, name, None)
            if callable(fn):
                fn()
                return {"auto_physics": "on", "via": name}
        return {"auto_physics": "unknown_on_method",
                "note": "no turn_on/set_on/enable on AutoPhysicsTool editor"}
    editor.turn_off()
    try:
        editor.turn_off_all_fulcrum_points()
    except Exception:
        pass
    return {"auto_physics": "off"}


OPS = {
    "ai.physics_tween": physics_tween,
    "ai.auto_interpolate": auto_interpolate,
    "ai.auto_physics": auto_physics,
}
