"""Reference-motion dataset: capture reference clips, then apply their poses /
retarget their motion onto the current rigged character.

Each clip is stored as dataset/<name>.json with per-joint world positions and
local euler rotations per frame (canonical joint names, namespace-stripped),
foot contacts, and hip height. Because reference and target are both standard
humanoid skeletons, poses transfer by joint role: we drive the target's rig
controller points to the reference joint world positions, scaled by the
hip-height ratio so it fits the target's proportions.
"""

from __future__ import annotations

import json
import math
import os

DATASET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "dataset")

# canonical roles we drive on the target (matching bone_map role keys). The
# target's own bone_map resolves each role to its actual controller point, so
# this is skeleton-agnostic on BOTH ends (Mixamo source -> CMU target, etc.).
APPLY_ROLES = [
    "hips", "spine0", "spine1", "chest", "neck", "head",
    "clavicle_l", "upperarm_l", "forearm_l", "hand_l",
    "clavicle_r", "upperarm_r", "forearm_r", "hand_r",
    "thigh_l", "calf_l", "foot_l", "toe_l",
    "thigh_r", "calf_r", "foot_r", "toe_r",
]


def _ensure_dir():
    os.makedirs(DATASET_DIR, exist_ok=True)


def clip_path(name: str) -> str:
    return os.path.join(DATASET_DIR, name + ".json")


def list_clips() -> list[dict]:
    _ensure_dir()
    out = []
    for fn in sorted(os.listdir(DATASET_DIR)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(DATASET_DIR, fn), encoding="utf-8") as f:
                d = json.load(f)
            out.append({
                "name": fn[:-5],
                "source": d.get("source"),
                "frames": d.get("frame_count"),
                "fps": d.get("fps"),
                "hip_height": d.get("hip_height"),
                "key_frames": d.get("key_frames"),
                "joints": len(d.get("joints", {})),
            })
        except Exception as e:
            out.append({"name": fn[:-5], "error": str(e)})
    return out


def load(name: str) -> dict:
    with open(clip_path(name), encoding="utf-8") as f:
        return json.load(f)


def _detect_key_frames(record: dict) -> dict:
    """Heuristic contact/passing frames from foot contact flags."""
    keys = {}
    contacts = record.get("contacts", {})
    for foot, tag in (("LeftFoot", "left"), ("RightFoot", "right")):
        flags = contacts.get(foot)
        if not flags:
            continue
        # first frame where contact starts (rising edge) = heel strike
        strikes = [i for i in range(len(flags))
                   if flags[i] and (i == 0 or not flags[i - 1])]
        lifts = [i for i in range(len(flags))
                 if not flags[i] and i > 0 and flags[i - 1]]
        if strikes:
            keys[f"{tag}_contact"] = strikes[0]
        if lifts:
            keys[f"{tag}_toe_off"] = lifts[0]
    return keys


def save_capture(name: str, source: str, record: dict) -> dict:
    _ensure_dir()
    record = dict(record)
    record["name"] = name
    record["source"] = source
    record["key_frames"] = _detect_key_frames(record)
    with open(clip_path(name), "w", encoding="utf-8") as f:
        json.dump(record, f)
    return {
        "saved": clip_path(name),
        "frames": record.get("frame_count"),
        "joints": record.get("joint_count"),
        "hip_height": record.get("hip_height"),
        "key_frames": record["key_frames"],
        "contacts_detected": list(record.get("contacts", {}).keys()),
    }


def pose_items(record: dict, ref_frame: int, target_bone_map: dict,
               roles=None, helper_geometry: dict | None = None) -> list[dict]:
    """Build transform.set items placing the TARGET's controller points at the
    reference clip's joint world positions for a frame, scaled by hip-height
    ratio. Resolves both sides by canonical role, so a clip captured from any
    skeleton applies onto any rigged character. If helper_geometry (from
    rig.helper_geometry) is given, also drives orientation helper points using
    the reference joint world rotation -> segment twist transfers (no floating)."""
    joints = record["joints"]
    r2j = record.get("role_to_joint", {})
    ref_h = record.get("hip_height") or 1.0
    tgt_roles = target_bone_map.get("roles", {})
    tgt_hips = tgt_roles.get("hips", {})
    target_h = (tgt_hips.get("world_position") or [0, ref_h, 0])[1]
    scale = (target_h / ref_h) if (target_h and ref_h) else 1.0

    # target spine chain (bone_map exposes it as an ordered list, not in roles)
    spine_chain = target_bone_map.get("spine_chain", [])

    def target_point(role):
        if role.startswith("spine"):
            try:
                idx = int(role[5:])
            except ValueError:
                idx = 0
            if idx < len(spine_chain):
                return spine_chain[idx].get("controllers", {}).get("MainPoint")
            return None
        tgt = tgt_roles.get(role)
        if tgt and tgt.get("controllers"):
            return tgt["controllers"].get("MainPoint")
        return None

    items = []
    want = set(roles) if roles else None
    for role in APPLY_ROLES:
        if want and role not in want:
            continue
        src_joint = r2j.get(role)
        if not src_joint or src_joint not in joints:
            continue
        point = target_point(role)
        if not point:
            continue
        fr = min(ref_frame, len(joints[src_joint]["world"]) - 1)
        wx, wy, wz = joints[src_joint]["world"][fr]
        items.append({
            "name": point,
            "global_position": [round(wx * scale, 3), round(wy * scale, 3),
                                round(wz * scale, 3)],
        })
        # orientation-aware: drive the segment's helper points using the
        # reference joint's WORLD rotation + the target's measured helper offset
        if helper_geometry and "world_rot" in joints[src_joint]:
            _append_helper_items(items, role, joints[src_joint], fr, scale,
                                 target_bone_map, helper_geometry)
    return items


def _euler_to_matrix(rx, ry, rz):
    """R = Rz @ Ry @ Rx from XYZ euler degrees (matches capture's decomp).
    Returns a 3x3 nested list."""
    x, y, z = math.radians(rx), math.radians(ry), math.radians(rz)
    cx, sx = math.cos(x), math.sin(x)
    cy, sy = math.cos(y), math.sin(y)
    cz, sz = math.cos(z), math.sin(z)
    # R = Rz @ Ry @ Rx, expanded
    return [
        [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
        [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
        [-sy,     cy * sx,                cy * cx],
    ]


def _matvec(R, v):
    return [R[0][0] * v[0] + R[0][1] * v[1] + R[0][2] * v[2],
            R[1][0] * v[0] + R[1][1] * v[1] + R[1][2] * v[2],
            R[2][0] * v[0] + R[2][1] * v[1] + R[2][2] * v[2]]


def _append_helper_items(items, role, src, fr, scale, target_bone_map,
                         helper_geometry):
    """Place the role's Additional/Direction/Self0 points from ref world rotation."""
    geo = helper_geometry.get("roles", {}).get(role)
    if not geo:
        return
    tgt_roles = target_bone_map.get("roles", {})
    spine_chain = target_bone_map.get("spine_chain", [])
    if role.startswith("spine"):
        try:
            idx = int(role[5:])
        except ValueError:
            idx = 0
        entry = spine_chain[idx] if idx < len(spine_chain) else None
    else:
        entry = tgt_roles.get(role)
    if not entry:
        return
    ctrls = entry.get("controllers", {})
    jw = src["world"][fr]
    jpos = [jw[0] * scale, jw[1] * scale, jw[2] * scale]
    R = _euler_to_matrix(*src["world_rot"][fr])
    for key, pt_name in (("additional", "AdditionalPoint"),
                         ("direction", "DirectionPoint"),
                         ("self0", "Self0Point")):
        off = geo.get(key)
        pn = ctrls.get(pt_name)
        if not off or not pn:
            continue
        ov = _matvec(R, [off[0] * scale, off[1] * scale, off[2] * scale])
        world = [jpos[0] + ov[0], jpos[1] + ov[1], jpos[2] + ov[2]]
        items.append({"name": pn,
                      "global_position": [round(world[0], 3), round(world[1], 3),
                                          round(world[2], 3)]})
