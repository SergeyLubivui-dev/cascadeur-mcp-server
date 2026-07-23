"""Animation baking and AI-assist operations."""

from . import resolve_objects, get_parent, obj_name


def anim_bake(ctx, frame_start=0, frame_end=None, name_re=None):
    """Bake joint LOCAL transforms per frame (fast path).

    Reads local_position + local_rotation directly off each joint's Transform
    behaviour (no global-matrix inversion) -> ~5x faster than deriving from
    global matrices. Returns per-joint per-frame [tx,ty,tz, rx,ry,rz]
    (rotation = XYZ euler degrees).
    """
    import math

    bv = ctx.bv()
    dv = ctx.dv()
    mv = ctx.mv()
    if frame_end is None:
        frame_end = dv.get_animation_size()
    frame_start, frame_end = int(frame_start), int(frame_end)
    frames_range = range(frame_start, frame_end)

    joints = resolve_objects(ctx, behaviour="Joint", name_re=name_re)
    ids = {o.to_string(): o for o in joints}

    lpos_ids = {}
    lrot_ids = {}
    parents = {}
    for o in joints:
        key = o.to_string()
        tr = bv.get_behaviour_by_name(o, "Transform")
        lpos_ids[key] = bv.get_behaviour_data(tr, "local_position")
        lrot_ids[key] = bv.get_behaviour_data(tr, "local_rotation")
        p = get_parent(ctx, o)
        parents[key] = p.to_string() if p is not None and p.to_string() in ids else None

    result_joints = []
    for o in joints:
        key = o.to_string()
        lp = lpos_ids[key]
        lr = lrot_ids[key]
        frames = []
        for f in frames_range:
            t = dv.get_data_value(lp, f)
            rot = dv.get_data_value(lr, f)
            try:
                e = rot.to_euler_angles_x_y_z()
                rx, ry, rz = (math.degrees(float(e[0])), math.degrees(float(e[1])),
                              math.degrees(float(e[2])))
            except Exception:
                rx = ry = rz = 0.0
            frames.append([round(float(t[0]), 6), round(float(t[1]), 6),
                           round(float(t[2]), 6), round(rx, 4), round(ry, 4),
                           round(rz, 4)])
        result_joints.append({
            "name": mv.get_object_name(o),
            "parent": mv.get_object_name(ids[parents[key]]) if parents[key] else None,
            "frames": frames,
        })

    return {
        "frame_start": frame_start,
        "frame_end": frame_end,
        "frame_count": frame_end - frame_start,
        "fps": 30,
        "joint_count": len(result_joints),
        "joints": result_joints,
    }


def capture(ctx, frame_start=0, frame_end=None, contact_threshold=3.0):
    """Capture the current animation as a normalized motion record for the
    reference dataset.

    Returns per-joint world positions AND local euler rotations (deg, XYZ) per
    frame (namespace stripped from joint names -> canonical), the hip height,
    foot-contact flags (foot world Y within contact_threshold of its clip
    minimum), and the hip world trajectory. Proportion-independent apply uses
    the rotations; quick retarget uses world positions scaled by hip height.
    """
    import numpy as np
    import math

    bv = ctx.bv()
    dv = ctx.dv()
    mv = ctx.mv()
    if frame_end is None:
        frame_end = dv.get_animation_size()
    frame_start, frame_end = int(frame_start), int(frame_end)
    frames = list(range(frame_start, frame_end))

    joints = resolve_objects(ctx, behaviour="Joint")
    ids = {o.to_string(): o for o in joints}
    parents = {}
    matrix_ids = {}
    names = {}
    for o in joints:
        key = o.to_string()
        names[key] = mv.get_object_name(o).split(":")[-1]
        beh = bv.get_behaviour_by_name(o, "Joint")
        matrix_ids[key] = bv.get_behaviour_data(beh, "global_matrix")
        p = get_parent(ctx, o)
        parents[key] = p.to_string() if p is not None and p.to_string() in ids else None

    # cache global matrices
    gm = {f: {k: np.array(dv.get_data_value(matrix_ids[k], f), dtype=np.float64)
              for k in ids} for f in frames}

    def euler_zyx(m):
        sy = max(-1.0, min(1.0, float(-m[2, 0])))
        ry = math.asin(sy)
        if abs(sy) < 0.9999:
            rx = math.atan2(m[2, 1], m[2, 2]); rz = math.atan2(m[1, 0], m[0, 0])
        else:
            rx = math.atan2(-m[1, 2], m[1, 1]); rz = 0.0
        return [round(math.degrees(rx), 3), round(math.degrees(ry), 3),
                round(math.degrees(rz), 3)]

    def norm_basis(r3):
        r3 = r3.copy()
        for cix in range(3):
            n = np.linalg.norm(r3[:, cix])
            if n > 1e-8:
                r3[:, cix] /= n
        return r3

    joints_out = {}
    for key in ids:
        nm = names[key]
        world = []
        lrot = []
        wrot = []
        for f in frames:
            m = gm[f][key]
            world.append([round(float(m[0, 3]), 2), round(float(m[1, 3]), 2),
                          round(float(m[2, 3]), 2)])
            p = parents[key]
            local = np.linalg.inv(gm[f][p]) @ m if p else m
            lrot.append(euler_zyx(norm_basis(local[:3, :3])))
            wrot.append(euler_zyx(norm_basis(m[:3, :3])))  # world orientation
        joints_out[nm] = {"world": world, "local_rot": lrot, "world_rot": wrot,
                          "parent": names.get(parents[key]) if parents[key] else None}

    # canonical role -> raw joint name (skeleton-agnostic mapping, so the
    # captured clip can be applied onto ANY rigged character by role).
    role_to_joint = {}
    try:
        from commands.mcp_bridge.ops import bonemap_ops as _bm
        for o in joints:
            raw = mv.get_object_name(o)
            core, side = _bm._normalize(raw)
            role, finfo = _bm._classify(core)
            nm = raw.split(":")[-1]
            if role == "finger" and finfo:
                key = "%s_%s_%d" % (finfo["finger"], side or "x", finfo["segment"])
                role_to_joint.setdefault(key, nm)
            elif role and role != "spine":
                key = role if side is None else "%s_%s" % (role, side)
                role_to_joint.setdefault(key, nm)
            elif role == "spine":
                # number spine chain by depth order of appearance
                idx = sum(1 for k in role_to_joint if k.startswith("spine"))
                role_to_joint["spine%d" % idx] = nm
    except Exception:
        pass

    # hip height (Hips world Y at first frame)
    hip_h = None
    for nm, data in joints_out.items():
        if nm.lower() in ("hips", "pelvis"):
            hip_h = data["world"][0][1]
            break
    if hip_h is None and "hips" in role_to_joint:
        hip_h = joints_out[role_to_joint["hips"]]["world"][0][1]

    # foot contacts (scale-invariant: within 18% of the foot's own Y range of
    # its minimum -> planted; works at any unit scale, incl. CMU's ~85x).
    contacts = {}
    foot_role_joints = [role_to_joint.get(r) for r in
                        ("foot_l", "foot_r", "toe_l", "toe_r")]
    for foot in [f for f in foot_role_joints if f and f in joints_out]:
        ys = [w[1] for w in joints_out[foot]["world"]]
        ymin, ymax = min(ys), max(ys)
        band = ymin + max(contact_threshold, 0.18 * (ymax - ymin))
        contacts[foot] = [bool(y <= band) for y in ys]

    return {
        "fps": 30,
        "frame_count": len(frames),
        "hip_height": hip_h,
        "joint_count": len(joints_out),
        "joints": joints_out,
        "role_to_joint": role_to_joint,
        "contacts": contacts,
    }


def auto_pose_update(ctx):
    """Run the AutoPosing ML update on the current frame (needs a session)."""
    tool = ctx.app.get_tools_manager().get_tool("AutoPosingTool")
    editor = tool.editor(ctx.app_scene())

    def mod(model, update, scene_updater, session):
        editor.update(session)

    ok = ctx.scene.modify_update_with_session("MCP: autoposing update", mod)
    return {"auto_posing": "updated" if ok else "failed"}


def root_motion(ctx, frame_start=0, frame_end=None):
    """Run Cascadeur's generative Root Motion over [frame_start, frame_end].

    Selects all tracks across the interval (needs >=2 keyframes) and triggers
    the RunRootMotion action. Extracts world trajectory from an in-place
    animation and drives the character root through space by foot contacts.
    Verified working on the free license (unlike AI inbetweening).
    """
    lv = ctx.lv()
    dv = ctx.dv()
    if frame_end is None:
        frame_end = dv.get_animation_size() - 1
    track_ids = list(lv.all_included_layer_ids([lv.root_id()]))
    sel = ctx.scene.get_layers_selector()
    sel.set_full_selection_by_parts(track_ids, int(frame_start), int(frame_end))
    ctx.app.get_action_manager().call_action("View.Inbetweening_RunRootMotion")
    return {"root_motion": "requested", "tracks": len(track_ids),
            "interval": [int(frame_start), int(frame_end)],
            "note": "runs on Cascadeur main thread; check the character root "
                    "translation afterwards"}


OPS = {
    "anim.bake": anim_bake,
    "anim.capture": capture,
    "ai.auto_pose_update": auto_pose_update,
    "ai.root_motion": root_motion,
}
