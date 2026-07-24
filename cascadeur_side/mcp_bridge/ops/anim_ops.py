"""Animation baking and AI-assist operations."""

from . import resolve_objects, get_parent, obj_name


def anim_bake(ctx, frame_start=0, frame_end=None, name_re=None, scale=True):
    """Bake joint LOCAL transforms per frame (fast path).

    Reads local_position + local_rotation directly off each joint's Transform
    behaviour (no global-matrix inversion) -> ~5x faster than deriving from
    global matrices. Returns per-joint per-frame [tx,ty,tz, rx,ry,rz]
    (rotation = XYZ euler degrees).

    scale=True (default) also reads local_scale and attaches a parallel
    "scale": [[sx,sy,sz], ...] field PER JOINT — but only when that joint is
    actually non-unit somewhere in the clip (so unit-scale rigs stay lean and
    the frame lists stay 6-wide for backward compatibility). apply_animation
    re-applies it when present, so a rig with baked/non-uniform bone scale
    transfers exactly (location + rotation + scale), not just loc+rot.
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
    lscl_ids = {}
    parents = {}
    for o in joints:
        key = o.to_string()
        tr = bv.get_behaviour_by_name(o, "Transform")
        lpos_ids[key] = bv.get_behaviour_data(tr, "local_position")
        lrot_ids[key] = bv.get_behaviour_data(tr, "local_rotation")
        if scale:
            try:
                sid = bv.get_behaviour_data(tr, "local_scale")
                lscl_ids[key] = sid if not sid.is_null() else None
            except Exception:
                lscl_ids[key] = None
        p = get_parent(ctx, o)
        parents[key] = p.to_string() if p is not None and p.to_string() in ids else None

    result_joints = []
    for o in joints:
        key = o.to_string()
        lp = lpos_ids[key]
        lr = lrot_ids[key]
        sid = lscl_ids.get(key)
        frames = []
        scales = []
        non_unit = False
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
            if sid is not None:
                s = dv.get_data_value(sid, f)
                sx, sy, sz = float(s[0]), float(s[1]), float(s[2])
                scales.append([round(sx, 6), round(sy, 6), round(sz, 6)])
                if abs(sx - 1.0) > 1e-4 or abs(sy - 1.0) > 1e-4 or abs(sz - 1.0) > 1e-4:
                    non_unit = True
        jout = {
            "name": mv.get_object_name(o),
            "parent": mv.get_object_name(ids[parents[key]]) if parents[key] else None,
            "frames": frames,
        }
        if non_unit:
            jout["scale"] = scales
        result_joints.append(jout)

    return {
        "frame_start": frame_start,
        "frame_end": frame_end,
        "frame_count": frame_end - frame_start,
        "fps": 30,
        "joint_count": len(result_joints),
        "joints": result_joints,
    }


def apply_local(ctx, joints, frame=None, fk=True):
    """Set FULL local transforms (position + rotation + scale) per joint — the
    correct way to transfer a pose so bones keep their orientation (no twisted
    legs from IK guessing). joints: [{"name": <joint>, "local_position":[x,y,z],
    "local_rotation":[rx,ry,rz] euler DEGREES, "local_scale":[sx,sy,sz]}] (any
    subset of the three). Matches joints by name suffix (namespace-agnostic).
    fk=True switches the object tracks to FK on this frame first so the local
    transforms are respected instead of being overridden by IK.
    """
    import numpy as np
    import math
    csc = ctx.csc
    bv = ctx.bv()
    mv = ctx.mv()
    if frame is None:
        frame = ctx.scene.get_current_frame()
    frame = int(frame)

    by_suffix = {}
    for o in resolve_objects(ctx, behaviour="Joint"):
        by_suffix[mv.get_object_name(o).split(":")[-1]] = o

    plan = []          # (data_id, value) for position/rotation
    scale_plan = []    # (data_id, value) for scale — applied in a SEPARATE pass
    touched = []       # objects, for FK switch
    missing = []
    for j in joints:
        suffix = j["name"].split(":")[-1]
        o = by_suffix.get(suffix)
        if o is None:
            missing.append(suffix)
            continue
        tr = bv.get_behaviour_by_name(o, "Transform")
        if tr.is_null():
            continue
        touched.append(o)
        if "local_position" in j:
            plan.append((bv.get_behaviour_data(tr, "local_position"),
                         np.array(j["local_position"], dtype=np.float32)))
        if "local_rotation" in j:
            e = j["local_rotation"]
            # MUST match the bake's decomposition (rot.to_euler_angles_x_y_z),
            # else compound rotations (arms) come out wrong. Use the x_y_z
            # euler->quaternion inverse, not the differently-ordered from_euler.
            q = csc.math.euler_angles_to_quaternion_x_y_z(
                np.array([math.radians(float(e[0])), math.radians(float(e[1])),
                          math.radians(float(e[2]))], dtype=np.float32))
            rot = csc.math.Rotation.from_quaternion(q)
            plan.append((bv.get_behaviour_data(tr, "local_rotation"), rot))
        if "local_scale" in j:
            scale_plan.append((bv.get_behaviour_data(tr, "local_scale"),
                               np.array(j["local_scale"], dtype=np.float32)))

    lv = ctx.lv()

    def mod(model, update, scene_updater):
        de = model.data_editor()
        if fk:
            le = model.layers_editor()
            for o in touched:
                try:
                    lid = lv.layer_id_by_obj_id(o)

                    def mod_section(section):
                        section.key.common.ik_fk = csc.layers.layer.IkFk.FK
                    le.set_fixed_interpolation_or_key_if_need(lid, frame, True)
                    le.change_section(frame, lid, mod_section)
                except Exception:
                    pass
        actuals = set()
        for did, val in plan:
            if not did.is_null():
                de.set_data_value(did, frame, val)
                actuals.add(did)
        scene_updater.run_update(actuals, frame)

    ctx.scene.modify_update("MCP: apply local transforms", mod)

    # scale in its OWN modify_update — a scale write batched with position/
    # rotation in the same run_update is silently dropped (verified).
    if scale_plan:
        def mod_scale(model, update, scene_updater):
            de = model.data_editor()
            actuals = set()
            for did, val in scale_plan:
                if not did.is_null():
                    de.set_data_value(did, frame, val)
                    actuals.add(did)
            scene_updater.run_update(actuals, frame)
        ctx.scene.modify_update("MCP: apply local scale", mod_scale)
    return {"applied": len(plan), "joints": len(touched), "frame": frame,
            "missing": missing[:8]}


def apply_animation(ctx, joints, frame_start=0, fk=True, set_clip=True):
    """Apply a WHOLE animation by full local transforms per joint per frame — the
    correct, no-twist retarget. joints uses the anim.bake format:
    [{"name": <joint>, "frames": [[tx,ty,tz, rx,ry,rz(deg)], ...]}]. Sets each
    joint's local_position + local_rotation for every frame in FK, so all bone
    orientations transfer exactly (unlike point-position retarget which twists).
    Matches joints by name suffix. Runs in one modify_update.
    """
    import numpy as np
    import math
    csc = ctx.csc
    bv = ctx.bv()
    mv = ctx.mv()
    lv = ctx.lv()

    by_suffix = {}
    for o in resolve_objects(ctx, behaviour="Joint"):
        by_suffix[mv.get_object_name(o).split(":")[-1]] = o

    n = max((len(j.get("frames", [])) for j in joints), default=0)
    if set_clip and n > 0:
        def clipmod(model, update, scene_updater):
            le = model.layers_editor()
            default_layer = lv.default_layer_id()
            le.set_section(csc.layers.layer.Section(), frame_start + n - 1,
                           default_layer)
            model.fit_animation_size_by_layers()
            scene_updater.generate_update()
        ctx.scene.modify_update("MCP: clip length", clipmod)

    matched = []
    for j in joints:
        o = by_suffix.get(j["name"].split(":")[-1])
        if o is not None:
            matched.append((o, j["frames"], j.get("scale")))

    def to_rot(rx, ry, rz):
        q = csc.math.euler_angles_to_quaternion_x_y_z(
            np.array([math.radians(rx), math.radians(ry), math.radians(rz)],
                     dtype=np.float32))
        return csc.math.Rotation.from_quaternion(q)

    n_scaled = sum(1 for _, _, s in matched if s)

    def mod(model, update, scene_updater):
        de = model.data_editor()
        le = model.layers_editor()
        actuals = set()
        for o, frames, _scales in matched:
            tr = bv.get_behaviour_by_name(o, "Transform")
            lpid = bv.get_behaviour_data(tr, "local_position")
            lrid = bv.get_behaviour_data(tr, "local_rotation")
            if fk:
                try:
                    lid = lv.layer_id_by_obj_id(o)

                    def mod_section(section):
                        section.key.common.ik_fk = csc.layers.layer.IkFk.FK
                        section.interval.common.ik_fk = csc.layers.layer.IkFk.FK
                    le.set_fixed_interpolation_or_key_if_need(lid, frame_start, True)
                    le.change_section(frame_start, lid, mod_section)
                except Exception:
                    pass
            for fi, fr in enumerate(frames):
                f = frame_start + fi
                de.set_data_value(lpid, f, np.array(fr[:3], dtype=np.float32))
                de.set_data_value(lrid, f, to_rot(fr[3], fr[4], fr[5]))
                actuals.add(lpid)
                actuals.add(lrid)
        scene_updater.run_update(actuals, frame_start)

    ctx.scene.modify_update("MCP: apply animation", mod)

    # local_scale MUST be written in a SEPARATE modify_update: a scale write
    # batched with local_position/local_rotation in the same run_update is
    # silently dropped (verified — combined write kept the old scale). Only
    # touch scale when a joint actually carries a non-unit scale channel.
    if n_scaled:
        def mod_scale(model, update, scene_updater):
            de = model.data_editor()
            actuals = set()
            for o, frames, scales in matched:
                if not scales:
                    continue
                tr = bv.get_behaviour_by_name(o, "Transform")
                try:
                    sid = bv.get_behaviour_data(tr, "local_scale")
                except Exception:
                    continue
                if sid.is_null():
                    continue
                for fi in range(len(frames)):
                    if fi < len(scales):
                        de.set_data_value(sid, frame_start + fi,
                                          np.array(scales[fi], dtype=np.float32))
                        actuals.add(sid)
            scene_updater.run_update(actuals, frame_start)
        ctx.scene.modify_update("MCP: apply animation scale", mod_scale)

    return {"joints": len(matched), "frames": n, "scaled_joints": n_scaled,
            "frame_range": [frame_start, frame_start + n - 1]}


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
    "anim.apply_local": apply_local,
    "anim.apply_animation": apply_animation,
    "anim.capture": capture,
    "ai.auto_pose_update": auto_pose_update,
    "ai.root_motion": root_motion,
}
