"""Shared helpers for bridge op handlers.

Every op handler has signature ``handler(ctx, **args) -> jsonable`` where ``ctx`` is
``exec_bridge.Ctx`` (fields: csc, scene, app; helpers: mv/bv/dv/lv/app_scene).
Handlers are collected from each module's ``OPS`` dict.
"""

import re


def to_jsonable(v):
    """Convert csc/numpy values into plain JSON-friendly structures."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    try:
        import numpy as np
        if isinstance(v, np.ndarray):
            return [to_jsonable(x) for x in v.tolist()]
        if isinstance(v, np.integer):
            return int(v)
        if isinstance(v, np.floating):
            return float(v)
    except Exception:
        pass
    if isinstance(v, dict):
        return {str(k): to_jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set, frozenset)):
        return [to_jsonable(x) for x in v]
    to_string = getattr(v, "to_string", None)
    if callable(to_string):
        try:
            return to_string()
        except Exception:
            pass
    # csc.math.Rotation -> euler degrees
    to_euler = getattr(v, "to_euler_angles_x_y_z", None)
    if callable(to_euler):
        try:
            import math
            return {"euler_deg_xyz": [round(math.degrees(float(a)), 4)
                                      for a in to_euler()]}
        except Exception:
            pass
    # csc.math.Quaternion / Rotation best effort
    for attrs in (("w", "x", "y", "z"),):
        if all(hasattr(v, a) for a in attrs):
            try:
                return {a: float(getattr(v, a)) for a in attrs}
            except Exception:
                pass
    return repr(v)


def obj_name(ctx, obj_id):
    try:
        return ctx.mv().get_object_name(obj_id)
    except Exception:
        return "<unnamed>"


def resolve_objects(ctx, names=None, ids=None, name_re=None, behaviour=None,
                    limit=None):
    """Resolve scene objects by exact names, id strings, regex and/or behaviour.

    Returns list of ObjectId. With no filters returns all objects.
    """
    mv = ctx.mv()
    result = []
    if ids:
        wanted = set(ids)
        for o in mv.get_objects():
            if o.to_string() in wanted:
                result.append(o)
        return result
    if names:
        for n in names:
            result.extend(mv.get_objects(n))
        return result

    objs = mv.get_objects()
    if behaviour:
        bv = ctx.bv()
        owned = set()
        for bh in bv.get_behaviours(behaviour):
            owned.add(bv.get_behaviour_owner(bh).to_string())
        objs = [o for o in objs if o.to_string() in owned]
    if name_re:
        rx = re.compile(name_re)
        objs = [o for o in objs if rx.search(mv.get_object_name(o))]
    if limit:
        objs = objs[:limit]
    return objs


def behaviour_names_of(ctx, obj_id):
    bv = ctx.bv()
    names = []
    try:
        for bh in bv.get_behaviours(obj_id):
            try:
                names.append(bv.get_behaviour_name(bh))
            except Exception:
                pass
    except Exception:
        pass
    return names


def get_parent(ctx, obj_id):
    """Return parent ObjectId via the Basic behaviour, or None."""
    bv = ctx.bv()
    try:
        basic = bv.get_behaviour_by_name(obj_id, "Basic")
        if basic.is_null():
            return None
        parent = bv.get_behaviour_object(basic, "parent")
        if parent.is_null():
            return None
        return parent
    except Exception:
        return None
