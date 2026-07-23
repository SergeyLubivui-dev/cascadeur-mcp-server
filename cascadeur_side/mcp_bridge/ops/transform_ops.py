"""Reading and writing object transforms (positions/rotations) per frame."""

from . import to_jsonable, resolve_objects, obj_name

_DATA_CANDIDATES = (
    "position", "global_position", "local_position", "local_rotation",
    "local_scale",
)


def _transform_datas(ctx, obj_id):
    """Map of data_name -> DataId available on the object.

    'position' is the object's own "Position" data node — for rig point
    controllers this is the true INPUT the manipulator writes to
    (Transform.global_position is a computed output there).
    """
    bv = ctx.bv()
    dv = ctx.dv()
    found = {}
    try:
        pos_id = dv.get_data_id(obj_id, "Position")
        if not pos_id.is_null():
            found["position"] = pos_id
    except Exception:
        pass
    for beh_name in ("Transform", "Joint"):
        try:
            beh = bv.get_behaviour_by_name(obj_id, beh_name)
        except Exception:
            continue
        if beh.is_null():
            continue
        names = _DATA_CANDIDATES if beh_name == "Transform" else ("global_matrix",)
        for dn in names:
            try:
                did = bv.get_behaviour_data(beh, dn)
                if not did.is_null():
                    found[dn] = did
            except Exception:
                pass
    return found


def transform_get(ctx, names=None, ids=None, name_re=None, behaviour=None,
                  frame=None, limit=100, with_matrix=False):
    dv = ctx.dv()
    if frame is None:
        frame = ctx.scene.get_current_frame()
    objs = resolve_objects(ctx, names=names, ids=ids, name_re=name_re,
                           behaviour=behaviour, limit=limit)
    out = []
    for o in objs:
        datas = _transform_datas(ctx, o)
        item = {"name": obj_name(ctx, o), "id": o.to_string()}
        for dn, did in datas.items():
            if dn == "global_matrix" and not with_matrix:
                # still derive world position from the matrix
                try:
                    m = dv.get_data_value(did, int(frame))
                    item["world_position_from_matrix"] = to_jsonable(m[:3, 3])
                except Exception:
                    pass
                continue
            try:
                item[dn] = to_jsonable(dv.get_data_value(did, int(frame)))
            except Exception:
                try:
                    item[dn] = to_jsonable(dv.get_data_value(did))
                except Exception:
                    pass
        out.append(item)
    return {"frame": int(frame), "count": len(out), "transforms": out}


def _coerce_like(ctx, current, value):
    """Build a value of the same type as `current` from a plain list."""
    import numpy as np
    if isinstance(current, np.ndarray):
        return np.array(value, dtype=current.dtype).reshape(current.shape)
    if isinstance(current, float):
        return float(value)
    if isinstance(current, int):
        return int(value)
    csc = ctx.csc
    if isinstance(current, csc.math.Quaternion):
        # value: [w, x, y, z]
        try:
            return csc.math.Quaternion(*[float(v) for v in value])
        except Exception:
            q = csc.math.Quaternion()
            q.w, q.x, q.y, q.z = [float(v) for v in value]
            return q
    if isinstance(current, csc.math.Rotation):
        # value: [x, y, z] euler degrees
        import math
        return csc.math.Rotation.from_euler(math.radians(float(value[0])),
                                            math.radians(float(value[1])),
                                            math.radians(float(value[2])))
    return value


def transform_set(ctx, items, frame=None, set_key=True):
    """Set transform data values on a frame and run the rig update.

    items: [{"name": str (or "id"),
             "global_position"|"local_position"|"local_rotation"|"local_scale": [..]}]
    """
    dv = ctx.dv()
    if frame is None:
        frame = ctx.scene.get_current_frame()
    frame = int(frame)

    plan = []  # (data_id, coerced_value)
    touched_objs = []
    errors = []
    for item in items:
        objs = resolve_objects(ctx, names=[item["name"]] if item.get("name") else None,
                               ids=[item["id"]] if item.get("id") else None)
        if not objs:
            errors.append("object not found: %r" % (item.get("name") or item.get("id")))
            continue
        o = objs[0]
        datas = _transform_datas(ctx, o)
        # For rig point controllers, "global_position" is a computed output;
        # route writes to the point's own "Position" input instead.
        aliases = dict(item)
        if "position" in datas and "global_position" in aliases \
                and "position" not in aliases:
            aliases["position"] = aliases.pop("global_position")
        matched = False
        for dn in _DATA_CANDIDATES:
            if dn not in aliases:
                continue
            if dn not in datas:
                errors.append("%s has no %s data" % (obj_name(ctx, o), dn))
                continue
            did = datas[dn]
            current = dv.get_data_value(did, frame)
            try:
                plan.append((did, _coerce_like(ctx, current, aliases[dn])))
                matched = True
            except Exception as e:
                errors.append("%s.%s: %s" % (obj_name(ctx, o), dn, e))
        if matched:
            touched_objs.append(o)

    if plan:
        lv = ctx.lv()

        def mod(model, update, scene_updater):
            de = model.data_editor()
            actuals = set()
            for did, value in plan:
                de.set_data_value(did, frame, value)
                actuals.add(did)
            if set_key:
                le = model.layers_editor()
                for o in touched_objs:
                    try:
                        track = lv.layer_id_by_obj_id(o)
                        le.set_fixed_interpolation_or_key_if_need(track, frame, True)
                    except Exception:
                        pass
                model.set_fixed_interpolation_if_need(actuals, frame)
            scene_updater.run_update(actuals, frame)

        ctx.scene.modify_update("MCP: set transforms", mod)

    return {"applied": len(plan), "frame": frame, "errors": errors}


OPS = {
    "transform.get": transform_get,
    "transform.set": transform_set,
}
