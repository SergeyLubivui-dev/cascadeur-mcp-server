"""Canonical bone-role mapping: works across naming conventions.

Classifies scene joints into canonical roles (hips, spine chain, head, limbs,
fingers) regardless of naming convention (Mixamo, UE4/UE5, CC3/AccuRig, Daz,
custom), and links each joint to its rig controller points. Animation recipes
address roles, not literal names.
"""

import re

from . import resolve_objects, get_parent, obj_name

# (role, regex on normalized core name). Order matters: first match wins.
# Normalized = namespace stripped, lowercased, separators removed, side removed.
_ROLE_PATTERNS = [
    ("hips",     r"^(hips|pelvis|hip|cog|bip01)$"),
    ("spine",    r"^(spine|spine0?1|spine0?2|spine0?3|spine0?4|stomach|abdomen2?|waist)$"),
    ("chest",    r"^(chest|upperchest|spine0?[45]|chestupper)$"),
    ("neck",     r"^(neck|neck0?1|neck0?2)$"),
    ("head",     r"^head$"),
    ("head_end", r"^(headtop.*|head.?end.*|headnub)$"),
    ("clavicle", r"^(shoulder|clavicle|collar|clav)$"),
    ("upperarm", r"^(arm|upperarm|uparm|bicep)$"),
    ("forearm",  r"^(forearm|lowerarm|elbow|lowarm)$"),
    ("hand",     r"^(hand|wrist)$"),
    ("thigh",    r"^(upleg|thigh|upperleg|uplegroll)$"),
    ("calf",     r"^(calf|shin|lowerleg|knee|leg)$"),  # bare "leg" resolved by parent
    ("foot",     r"^(foot|ankle)$"),
    ("toe",      r"^(toebase|ball|toe|toes)$"),
    ("toe_end",  r"^(toe.?end.*|toesend|toenub)$"),
]

# Exact normalized-core -> role aliases for terse conventions (CMU, BVH mocap).
# Checked before the regex patterns. Disambiguates cases where an abbreviation
# means a different bone than the full word (CMU "shldr"=upperarm vs Mixamo
# "shoulder"=clavicle).
_ALIASES = {
    "abdomen": "spine", "abdomen2": "chest", "lowerback": "spine",
    "collar": "clavicle", "shldr": "upperarm", "uparm": "upperarm",
    "forearm": "forearm", "thigh": "thigh", "shin": "calf",
    "buttock": None,  # pelvis offset joint — ignore
    "eye": None, "lowerarm": "forearm",
}

_FINGERS = ("thumb", "index", "middle", "ring", "pinky", "little", "mid")

_SIDE_PATTERNS = [
    (re.compile(r"^left|^l[_\-. ]|[_\-. ]l$|_l_|^lft"), "l"),
    (re.compile(r"^right|^r[_\-. ]|[_\-. ]r$|_r_|^rgt"), "r"),
]


def _strip_namespace(name):
    for sep in (":", "|"):
        if sep in name:
            name = name.rsplit(sep, 1)[1]
    return name


def _normalize(raw):
    """Return (core, side). core: lowercased, side markers and separators removed."""
    n = _strip_namespace(raw).lower()
    n = re.sub(r"^(cc_base_|bip01[_ ]?|mixamorig\d*:?)", "", n)
    side = None
    # explicit word/side affixes
    m = re.match(r"^(left|right)(.*)$", n)
    if m:
        side = "l" if m.group(1) == "left" else "r"
        n = m.group(2)
    else:
        m = re.match(r"^([lr])[_\-. ](.*)$", n)
        if m:
            side = m.group(1)
            n = m.group(2)
        else:
            m = re.match(r"^(.*?)[_\-. ]([lr])$", n)
            if m:
                side = m.group(2)
                n = m.group(1)
    # camelCase side prefix with no separator: rShldr, lThigh, rIndex1
    if side is None:
        m = re.match(r"^([lr])([a-z]*[0-9]*)$", _strip_namespace(raw))
        # re-derive from the ORIGINAL cased string to catch the upper boundary
        cm = re.match(r"^([lr])([A-Z].*)$", _strip_namespace(raw))
        if cm:
            side = cm.group(1).lower()
            n = re.sub(r"[_\-. ]", "", cm.group(2).lower())
    n = re.sub(r"[_\-. ]", "", n)
    return n, side


def _classify(core):
    """Return (role, finger_info|None). core is normalized without side."""
    for f in _FINGERS:
        m = re.match(r"^(?:hand)?(%s)(\d)?(end)?$" % f, core)
        if m:
            fname = "thumb" if f == "thumb" else \
                ("pinky" if f in ("pinky", "little") else
                 ("middle" if f == "mid" else f))
            seg = int(m.group(2)) if m.group(2) else 0
            return ("finger", {"finger": fname, "segment": seg,
                               "is_end": bool(m.group(3))})
    if core in _ALIASES:
        role = _ALIASES[core]
        return (role, None) if role else (None, None)
    for role, pattern in _ROLE_PATTERNS:
        if re.match(pattern, core):
            return (role, None)
    return (None, None)


def bone_map(ctx):
    """Map scene joints to canonical roles + their controller points.

    Returns {"roles": {role[_l|_r]: {joint, controllers{main,additional,...},
    world_position}}, "fingers": {...}, "spine_chain": [...], "unmapped": [...],
    "namespace": str, "controller_suffixes": [...]}.
    """
    mv = ctx.mv()
    bv = ctx.bv()
    dv = ctx.dv()

    joints = resolve_objects(ctx, behaviour="Joint")
    joint_names = [mv.get_object_name(o) for o in joints]

    # controllers: any Point-behaviour object named "<joint>_<Suffix>Point"
    controllers = {}
    suffixes = set()
    try:
        for bh in bv.get_behaviours("Point"):
            o = bv.get_behaviour_owner(bh)
            pname = mv.get_object_name(o)
            m = re.match(r"^(.*)_([A-Za-z0-9]+Point)$", pname)
            if m:
                controllers.setdefault(m.group(1), {})[m.group(2)] = pname
                suffixes.add(m.group(2))
    except Exception:
        pass

    # namespace detection
    namespaces = {}
    for n in joint_names:
        ns = n.rsplit(":", 1)[0] + ":" if ":" in n else ""
        namespaces[ns] = namespaces.get(ns, 0) + 1
    namespace = max(namespaces, key=namespaces.get) if namespaces else ""

    roles = {}
    fingers = {}
    spine_chain = []
    unmapped = []

    def joint_entry(o, raw):
        entry = {"joint": raw, "controllers": controllers.get(raw, {})}
        try:
            beh = bv.get_behaviour_by_name(o, "Joint")
            gm = bv.get_behaviour_data(beh, "global_matrix")
            mmat = dv.get_data_value(gm, ctx.scene.get_current_frame())
            entry["world_position"] = [round(float(v), 3) for v in mmat[:3, 3]]
        except Exception:
            pass
        return entry

    ids = {o.to_string(): raw for o, raw in zip(joints, joint_names)}

    def parent_core(o):
        p = get_parent(ctx, o)
        if p is None or p.to_string() not in ids:
            return None
        return _normalize(ids[p.to_string()])[0]

    for o, raw in zip(joints, joint_names):
        core, side = _normalize(raw)
        role, finfo = _classify(core)
        # bare "leg" is ambiguous: Mixamo Leg = calf, some rigs leg = thigh
        if role == "calf" and core == "leg" and parent_core(o) in ("hips", "pelvis"):
            role = "thigh"
        if role == "finger":
            side_key = side or "x"
            fkey = "%s_%s" % (finfo["finger"], side_key)
            fingers.setdefault(fkey, []).append(
                dict(joint_entry(o, raw), segment=finfo["segment"],
                     is_end=finfo["is_end"]))
        elif role == "spine":
            spine_chain.append(joint_entry(o, raw))
        elif role is not None:
            key = role if side is None else "%s_%s" % (role, side)
            if key in roles:
                if not role.endswith("_end"):
                    unmapped.append(raw + " (duplicate role %s)" % key)
            else:
                roles[key] = joint_entry(o, raw)
        else:
            unmapped.append(raw)

    for fjoints in fingers.values():
        fjoints.sort(key=lambda e: e["segment"])

    return {
        "joint_count": len(joints),
        "namespace": namespace,
        "controller_suffixes": sorted(suffixes),
        "roles": roles,
        "spine_chain": spine_chain,
        "fingers": {k: [dict(e, controllers=e["controllers"]) for e in v]
                    for k, v in fingers.items()},
        "finger_summary": {k: len(v) for k, v in sorted(fingers.items())},
        "unmapped": unmapped,
    }


def helper_geometry(ctx, frame=0):
    """Per-role local offsets of the rig's orientation helper points
    (AdditionalPoint / DirectionPoint / Self0Point) relative to the joint, in
    the joint's LOCAL frame at `frame`. Measured once on a rest pose, these let
    an orientation-aware retarget reconstruct segment twist:
    helper_world = joint_world_pos + joint_world_rot @ offset_local.
    Returns {role: {joint_len: float, additional: [x,y,z], direction: [...],
    self0: [...]}} (only helpers that exist).
    """
    import numpy as np
    bv = ctx.bv()
    dv = ctx.dv()
    mv = ctx.mv()
    bm = bone_map(ctx)
    ns = bm["namespace"]
    frame = int(frame)

    def joint_world(role_entry):
        objs = mv.get_objects(role_entry["joint"])
        if not objs:
            return None
        o = objs[0]
        j = bv.get_behaviour_by_name(o, "Joint")
        if j.is_null():
            return None
        m = np.array(dv.get_data_value(bv.get_behaviour_data(j, "global_matrix"),
                                       frame), dtype=np.float64)
        return m

    def point_world(pname):
        objs = mv.get_objects(pname)
        if not objs:
            return None
        try:
            pid = dv.get_data_id(objs[0], "Position")
            if pid.is_null():
                return None
            return np.array(dv.get_data_value(pid, frame), dtype=np.float64)
        except Exception:
            return None

    out = {}
    roles = dict(bm.get("roles", {}))
    for i, sp in enumerate(bm.get("spine_chain", [])):
        roles["spine%d" % i] = sp

    for role, entry in roles.items():
        m = joint_world(entry)
        if m is None:
            continue
        jpos = m[:3, 3]
        R = m[:3, :3].copy()
        for c in range(3):
            n = np.linalg.norm(R[:, c])
            if n > 1e-8:
                R[:, c] /= n
        ctrls = entry.get("controllers", {})
        geo = {}
        for pt_name, key in (("AdditionalPoint", "additional"),
                             ("DirectionPoint", "direction"),
                             ("Self0Point", "self0")):
            pn = ctrls.get(pt_name)
            if not pn:
                continue
            pw = point_world(pn)
            if pw is None:
                continue
            local = R.T @ (pw - jpos)
            geo[key] = [round(float(local[0]), 3), round(float(local[1]), 3),
                        round(float(local[2]), 3)]
        if geo:
            out[role] = geo
    return {"namespace": ns, "roles": out}


OPS = {
    "rig.bone_map": bone_map,
    "rig.helper_geometry": helper_geometry,
}
