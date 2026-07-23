"""Server-side IK-correctness guard: keeps controller targets inside the rig's
reachable range and above the ground, so hand/foot points are placed correctly
without over-stretching or clipping through the floor.

Usage: fetch the rig model once (bridge op rig.model), cache it, then run
`clamp_items(items, model)` on any transform.set items before sending them.
"""

from __future__ import annotations

import math

_cache: dict[str, dict] = {}


def get_model(bridge, force: bool = False) -> dict:
    """Fetch+cache the rig model for the current character."""
    key = "current"
    if force or key not in _cache:
        model, _ = bridge.run_op("rig.model")
        _cache[key] = model
    return _cache[key]


def _v(p):
    return (float(p[0]), float(p[1]), float(p[2]))


def _dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def clamp_items(items: list[dict], model: dict, ground: bool = True,
                reach: bool = True, reach_frac: float = 0.98) -> tuple[list, list]:
    """Return (clamped_items, adjustments). Each item {name, global_position}.

    - reach: pull a limb target back onto the reachable sphere around its chain
      root (approximated as chain_root_rest + (hips_target - hips_rest)).
    - ground: raise a foot/toe target to at least ground_y.
    """
    ns = model.get("namespace", "")
    chains = model.get("chains", {})
    joint_rest = model.get("joint_rest", {})
    hips_rest = model.get("hips_rest", [0, 95, 0])
    ground_y = model.get("ground_y", 0.0)

    # target-point -> chain (reach + root joint)
    point_chain = {}
    for cname, ch in chains.items():
        if ch.get("target_point"):
            point_chain[ch["target_point"]] = ch

    # hips target in THIS pose (to shift chain roots); else use rest
    hips_pt = f"{ns}Hips_MainPoint"
    hips_target = hips_rest
    for it in items:
        if it["name"] == hips_pt:
            hips_target = it["global_position"]
            break
    shift = [hips_target[i] - hips_rest[i] for i in range(3)]

    adj = []
    out = []
    for it in items:
        name = it["name"]
        pos = list(_v(it["global_position"]))

        # ground clamp for feet/toes
        if ground and ("Foot_MainPoint" in name or "ToeBase_MainPoint" in name
                       or "Self0Point" in name):
            floor = ground_y + (0.0 if "ToeBase" in name else 12.5)
            if pos[1] < floor:
                adj.append(f"{name}: raised to ground ({round(pos[1],1)}->{floor})")
                pos[1] = floor

        # reach clamp for limb targets
        if reach and name in point_chain:
            ch = point_chain[name]
            root_rest = joint_rest.get(ch["root_joint"])
            if root_rest:
                root = [root_rest[i] + shift[i] for i in range(3)]
                d = _dist(pos, root)
                maxr = ch["reach"] * reach_frac
                if d > maxr and d > 1e-6:
                    f = maxr / d
                    pos = [root[i] + (pos[i] - root[i]) * f for i in range(3)]
                    adj.append(f"{name}: reach clamp ({round(d,1)}>{round(maxr,1)})")

        out.append({"name": name,
                    "global_position": [round(pos[0], 3), round(pos[1], 3),
                                        round(pos[2], 3)]})
    return out, adj


def rest_offset_item(model: dict, point_name: str, dx=0.0, dy=0.0, dz=0.0,
                     relative_to_hips: bool = False,
                     hips_target=None) -> dict:
    """Build a target from the point's REST position + an offset — the safe way
    to author ('lift the hand 20cm') without guessing absolute world coords."""
    rest = model.get("point_rest", {}).get(point_name)
    if rest is None:
        raise KeyError(point_name)
    base = list(rest)
    if relative_to_hips and hips_target is not None:
        hr = model.get("hips_rest", [0, 95, 0])
        base = [base[i] + (hips_target[i] - hr[i]) for i in range(3)]
    return {"name": point_name,
            "global_position": [round(base[0] + dx, 3), round(base[1] + dy, 3),
                                round(base[2] + dz, 3)]}
