"""Rig model extraction: bone lengths, chain reach, point rest positions, angle
constraints, ground — the data the server-side IK-correctness guard needs."""

from . import resolve_objects, get_parent


def rig_model(ctx):
    """Return a compact rig model for validation/clamping.

    chains: per limb, the controller point driven + the chain root joint + total
    reach (sum of segment lengths at rest). point_rest: rest world position of
    every controller point. hips_rest / ground for height reference.
    """
    import numpy as np
    bv = ctx.bv()
    dv = ctx.dv()
    mv = ctx.mv()

    # bone_map gives roles + controller points, namespace-agnostic
    from commands.mcp_bridge.ops import bonemap_ops as bm_mod
    bm = bm_mod.bone_map(ctx)
    ns = bm["namespace"]
    roles = bm["roles"]

    def joint_world(jname):
        objs = mv.get_objects(jname)
        if not objs:
            return None
        j = bv.get_behaviour_by_name(objs[0], "Joint")
        if j.is_null():
            return None
        m = np.array(dv.get_data_value(bv.get_behaviour_data(j, "global_matrix"), 0))
        return m[:3, 3].astype(float)

    def seg_len(a, b):
        pa, pb = joint_world(a), joint_world(b)
        if pa is None or pb is None:
            return 0.0
        return float(np.linalg.norm(pa - pb))

    def jn(role):
        r = roles.get(role)
        return r["joint"] if r else None

    def point(role):
        r = roles.get(role)
        if r:
            return r.get("controllers", {}).get("MainPoint")
        return None

    chains = {}
    for side in ("l", "r"):
        up = jn(f"upperarm_{side}"); fo = jn(f"forearm_{side}"); ha = jn(f"hand_{side}")
        if up and fo and ha:
            chains[f"arm_{side}"] = {
                "root_joint": up, "target_point": point(f"hand_{side}"),
                "reach": round(seg_len(up, fo) + seg_len(fo, ha), 2)}
        th = jn(f"thigh_{side}"); ca = jn(f"calf_{side}"); ft = jn(f"foot_{side}")
        if th and ca and ft:
            chains[f"leg_{side}"] = {
                "root_joint": th, "target_point": point(f"foot_{side}"),
                "reach": round(seg_len(th, ca) + seg_len(ca, ft), 2)}

    # rest world positions of controller points + chain-root joints
    point_rest = {}
    for role, r in roles.items():
        for pn in (r.get("controllers", {}) or {}).values():
            objs = mv.get_objects(pn)
            if not objs:
                continue
            try:
                pid = dv.get_data_id(objs[0], "Position")
                if not pid.is_null():
                    v = dv.get_data_value(pid, 0)
                    point_rest[pn] = [round(float(v[0]), 2), round(float(v[1]), 2),
                                      round(float(v[2]), 2)]
            except Exception:
                pass
    joint_rest = {}
    for role, r in roles.items():
        jw = joint_world(r["joint"])
        if jw is not None:
            joint_rest[r["joint"]] = [round(float(jw[0]), 2), round(float(jw[1]), 2),
                                      round(float(jw[2]), 2)]

    hips = roles.get("hips", {})
    hips_rest = hips.get("world_position") or [0, 95, 0]

    # ground = min foot Y at rest
    ground = 0.0
    fys = []
    for side in ("l", "r"):
        f = roles.get(f"foot_{side}", {}).get("joint")
        if f:
            w = joint_world(f)
            if w is not None:
                fys.append(float(w[1]))
    if fys:
        ground = round(min(fys) - 12.5, 2)  # ankle rest ~12.5 above ground

    return {
        "namespace": ns,
        "chains": chains,
        "point_rest": point_rest,
        "joint_rest": joint_rest,
        "hips_rest": hips_rest,
        "ground_y": ground,
    }


OPS = {"rig.model": rig_model}
