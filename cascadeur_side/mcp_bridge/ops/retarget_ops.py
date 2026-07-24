"""Cross-rig animation retarget: transfer a SOURCE clip onto the CURRENT rigged
character by matching bones (by name suffix, or by canonical role), transferring
rotations (proportion-independent, no twist) and scaling the root translation by
hip-height ratio. Weights are untouched — the target mesh follows its own rig.
"""


def _suffix(name):
    return name.split(":")[-1]


def retarget(ctx, source_joints, source_roles=None, source_hip_height=None,
             match="role", frame_start=0):
    """Apply a source clip onto the current character.

    source_joints: anim.bake-format list from the SOURCE character.
    source_roles:  role -> source joint name (from rig.bone_map of the source);
                   required for match="role".
    source_hip_height: source hips world Y (to scale root translation).
    match: "name" (direct suffix match — same naming, e.g. Mixamo->Mixamo) or
           "role" (canonical-role match — different naming, e.g. Mixamo->Cascy).
    """
    from commands.mcp_bridge.ops import bonemap_ops, anim_ops

    if match == "name":
        res = anim_ops.apply_animation(ctx, source_joints, frame_start=frame_start)
        res["match"] = "name"
        res["applied_joints"] = res.get("joints")
        return res

    # --- role match -------------------------------------------------------
    tgt = bonemap_ops.bone_map(ctx)
    tgt_roles = tgt.get("roles", {}) or {}
    role_to_tgt = {}
    tgt_hip = None
    for role, info in tgt_roles.items():
        role_to_tgt[role] = info.get("joint")
        if role in ("hips", "pelvis"):
            wp = info.get("world_position")
            if wp:
                tgt_hip = wp[1]

    src_by_suffix = {_suffix(j["name"]): j for j in source_joints}
    src_role_frames = {}
    for role, src_name in (source_roles or {}).items():
        j = src_by_suffix.get(_suffix(src_name))
        if j:
            src_role_frames[role] = j["frames"]

    hip_scale = None
    if source_hip_height and tgt_hip:
        try:
            hip_scale = float(tgt_hip) / float(source_hip_height)
        except Exception:
            hip_scale = None

    out = []
    matched = []
    unmatched = []
    for role, frames in src_role_frames.items():
        tjoint = role_to_tgt.get(role)
        if not tjoint:
            unmatched.append(role)
            continue
        is_root = role in ("hips", "pelvis")
        if is_root and hip_scale:
            s = hip_scale
            frames = [[f[0] * s, f[1] * s, f[2] * s, f[3], f[4], f[5]]
                      for f in frames]
        out.append({"name": tjoint, "frames": frames, "rot_only": not is_root})
        matched.append(role)

    res = anim_ops.apply_animation(ctx, out, frame_start=frame_start)
    res.update({
        "match": "role",
        "applied_joints": res.get("joints"),
        "matched_roles": len(matched),
        "roles": sorted(matched)[:40],
        "unmatched_source_roles": sorted(unmatched)[:20],
        "target_roles_without_source": sorted(
            r for r in role_to_tgt if r not in src_role_frames)[:20],
        "hip_scale": round(hip_scale, 3) if hip_scale else None,
    })
    return res


OPS = {
    "anim.retarget": retarget,
}
