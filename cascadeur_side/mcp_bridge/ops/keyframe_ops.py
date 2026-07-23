"""Timeline tracks (layers), keyframes, interpolation, IK/FK and fixation."""

from . import resolve_objects, obj_name

_INTERP = ("BEZIER", "LOW_AMPLITUDE_BEZIER", "LINEAR", "STEP", "FIXED", "NONE",
           "CLAMPED_BEZIER", "AI")  # AI = ML inbetweening (2025.3+)


def _iter_layers(ctx):
    lv = ctx.lv()
    for layer_id in lv.all_included_layer_ids([lv.root_id()]):
        yield layer_id, lv.layer(layer_id)


def _find_layers(ctx, track_names=None, object_names=None):
    """Resolve layer ids by track name and/or by object membership."""
    lv = ctx.lv()
    result = {}
    if track_names:
        wanted = set(track_names)
        for layer_id, layer in _iter_layers(ctx):
            if layer.header.name in wanted:
                result[layer_id.to_string()] = layer_id
    if object_names:
        for o in resolve_objects(ctx, names=object_names):
            try:
                lid = lv.layer_id_by_obj_id(o)
                result[lid.to_string()] = lid
            except Exception:
                pass
    if not track_names and not object_names:
        for layer_id, _ in _iter_layers(ctx):
            result[layer_id.to_string()] = layer_id
    return list(result.values())


def tracks_list(ctx, with_objects=False):
    mv = ctx.mv()
    out = []
    for layer_id, layer in _iter_layers(ctx):
        item = {
            "id": layer_id.to_string(),
            "name": layer.header.name,
            "visible": layer.is_visible,
            "locked": layer.is_locked,
            "object_count": len(layer.obj_ids),
        }
        if with_objects:
            item["objects"] = [mv.get_object_name(o) for o in layer.obj_ids]
        out.append(item)
    return {"count": len(out), "tracks": out}


def tracks_create(ctx, name, folder=None):
    lv = ctx.lv()
    result = {}

    def mod(model, update, scene_updater):
        le = model.layers_editor()
        parent = lv.root_id()
        result["id"] = le.create_layer(name, parent).to_string()

    ctx.scene.modify_update("MCP: create track", mod)
    return result


def tracks_move_objects(ctx, object_names, track_name):
    objs = resolve_objects(ctx, names=object_names)
    layers = _find_layers(ctx, track_names=[track_name])
    if not layers:
        raise ValueError("track not found: %r" % track_name)

    def mod(model, update, scene_updater):
        model.move_objects_to_layer(list(objs), layers[0])

    ctx.scene.modify_update("MCP: move objects to track", mod)
    return {"moved": [obj_name(ctx, o) for o in objs], "track": track_name}


def keys_list(ctx, track_names=None, object_names=None, start=0, end=None):
    dv = ctx.dv()
    lv = ctx.lv()
    if end is None:
        end = dv.get_animation_size()
    out = []
    for lid in _find_layers(ctx, track_names, object_names):
        layer = lv.layer(lid)
        frames = [f for f in range(int(start), int(end)) if layer.is_key(f)]
        sections = []
        for f in frames:
            try:
                sec = layer.section(f)
                sections.append({
                    "frame": f,
                    "interpolation": sec.interval.interpolation.name,
                    "ik_fk": sec.key.common.ik_fk.name,
                    "fixation": sec.key.common.fixation.name,
                })
            except Exception:
                sections.append({"frame": f})
        out.append({"track": layer.header.name, "id": lid.to_string(),
                    "keys": sections})
    return {"tracks": out}


def keys_set(ctx, frames, track_names=None, object_names=None):
    if isinstance(frames, int):
        frames = [frames]
    layers = _find_layers(ctx, track_names, object_names)

    def mod(model, update, scene_updater):
        le = model.layers_editor()
        for lid in layers:
            for f in frames:
                le.set_fixed_interpolation_or_key_if_need(lid, int(f), True)

    ctx.scene.modify_update("MCP: set keyframes", mod)
    return {"tracks": len(layers), "frames": frames}


def keys_delete(ctx, frames, track_names=None, object_names=None):
    if isinstance(frames, int):
        frames = [frames]
    layers = _find_layers(ctx, track_names, object_names)
    lv = ctx.lv()

    def mod(model, update, scene_updater):
        le = model.layers_editor()
        for lid in layers:
            layer = lv.layer(lid)
            for f in frames:
                if layer.is_key(int(f)):
                    le.unset_section(int(f), lid)

    ctx.scene.modify_update("MCP: delete keyframes", mod)
    return {"tracks": len(layers), "frames": frames}


def interval_set(ctx, frame, interpolation=None, ik_fk=None, fixation=None,
                 on_key=False, track_names=None, object_names=None):
    """Change interpolation/IK-FK/fixation of the section containing `frame`."""
    csc = ctx.csc
    if interpolation is not None and interpolation.upper() not in _INTERP:
        raise ValueError("interpolation must be one of %s" % (_INTERP,))
    layers = _find_layers(ctx, track_names, object_names)

    def mod_section(section):
        if interpolation is not None:
            section.interval.interpolation = getattr(
                csc.layers.layer.Interpolation, interpolation.upper())
        target = section.key.common if on_key else section.interval.common
        if ik_fk is not None:
            target.ik_fk = getattr(csc.layers.layer.IkFk, ik_fk.upper())
        if fixation is not None:
            fx = {"free": "Free", "fulcrum": "Fulcrum"}[fixation.lower()]
            target.fixation = getattr(csc.layers.layer.Fixation, fx)

    # One modify per track: batching several change_section calls into a single
    # modify only applies the first one (empirically).
    for lid in layers:
        def mod(model, update, scene_updater, _lid=lid):
            model.layers_editor().change_section(int(frame), _lid, mod_section)
        ctx.scene.modify_update("MCP: set interval properties", mod)
    return {"tracks": len(layers), "frame": frame}


OPS = {
    "tracks.list": tracks_list,
    "tracks.create": tracks_create,
    "tracks.move_objects": tracks_move_objects,
    "keys.list": keys_list,
    "keys.set": keys_set,
    "keys.delete": keys_delete,
    "interval.set": interval_set,
}
