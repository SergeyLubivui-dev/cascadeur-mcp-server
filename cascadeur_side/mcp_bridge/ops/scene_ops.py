"""Scene-level operations: info, tabs, open/save, current frame, clip length."""

from . import to_jsonable


def scene_info(ctx):
    mv = ctx.mv()
    dv = ctx.dv()
    app_scene = ctx.app_scene()
    sm = ctx.app.get_scene_manager()

    selected = []
    try:
        sel = ctx.scene.selector().selected()
        selected = [i for i in sel.ids if hasattr(i, "is_null")]
    except Exception:
        pass

    tabs = []
    try:
        current_name = app_scene.name()
        for s in sm.scenes():
            tabs.append({"name": s.name(), "path": s.get_path_name(),
                         "is_current": s.name() == current_name})
    except Exception:
        pass

    return {
        "name": app_scene.name(),
        "path": app_scene.get_path_name(),
        "current_frame": ctx.scene.get_current_frame(),
        "animation_frames": dv.get_animation_size(),
        "object_count": len(mv.get_objects()),
        "selected_count": len(selected),
        "tabs": tabs,
    }


def scene_new(ctx, make_current=True):
    sm = ctx.app.get_scene_manager()
    new_scene = sm.create_application_scene()
    if make_current:
        sm.set_current_scene(new_scene)
    return {"name": new_scene.name()}


def scene_open(ctx, path, new_tab=True):
    csc = ctx.csc
    sm = ctx.app.get_scene_manager()
    if new_tab:
        app_scene = sm.create_application_scene()
        sm.set_current_scene(app_scene)
    else:
        app_scene = sm.current_scene()
    csc.app.ProjectLoader.load_from(path.replace("\\", "/"), app_scene.domain_scene())
    return {"name": app_scene.name(), "path": path}


def scene_save(ctx, path=None):
    import os
    app_scene = ctx.app_scene()
    if path is None:
        path = app_scene.get_path_name()
        if not path:
            raise ValueError("Scene has no path yet; pass an explicit 'path'")
    app_scene.save(path.replace("\\", "/"))
    # save() returns False even on success; trust the file system instead.
    exists = os.path.isfile(path)
    return {"saved": exists, "path": path,
            "size": os.path.getsize(path) if exists else 0}


def scene_close_tab(ctx, name=None):
    sm = ctx.app.get_scene_manager()
    target = None
    if name is None:
        target = sm.current_scene()
    else:
        for s in sm.scenes():
            if s.name() == name:
                target = s
                break
    if target is None:
        raise ValueError("No scene tab named %r" % name)
    closed = target.name()
    sm.remove_application_scene(target)
    return {"closed": closed}


def scene_switch_tab(ctx, name):
    sm = ctx.app.get_scene_manager()
    for s in sm.scenes():
        if s.name() == name:
            sm.set_current_scene(s)
            return {"current": s.name()}
    raise ValueError("No scene tab named %r; open tabs: %s"
                     % (name, [s.name() for s in sm.scenes()]))


def scene_close_others(ctx, keep=None):
    """Close every scene tab EXCEPT the one named `keep` (default: the current
    tab). Frees memory — Cascadeur keeps each open tab's full scene resident and
    clears undo history once the process passes its RAM limit, so leaked tabs
    from repeated new_tab opens bloat it fast. Returns how many were closed."""
    sm = ctx.app.get_scene_manager()
    if keep is None:
        try:
            keep = sm.current_scene().name()
        except Exception:
            keep = None
    victims = [s for s in list(sm.scenes()) if s.name() != keep]
    closed = []
    for s in victims:
        nm = s.name()
        try:
            sm.remove_application_scene(s)
            closed.append(nm)
        except Exception:
            pass
    return {"closed": closed, "closed_count": len(closed), "kept": keep,
            "remaining": len(list(sm.scenes()))}


_PART_PATHS = {
    "cube": "objects/cube.partscasc",
    "sphere": "objects/sphere.partscasc",
    "cylinder": "objects/cylinder.partscasc",
    "plane": "objects/plane.partscasc",
    "locator": "objects/locator.partscasc",
}


def _write_constant(de, dv, data_id, value):
    """Write `value` so it is CONSTANT across the whole clip — the canonical
    Static/Animation-aware pattern from Cascadeur's own restore_values.py.
    Fixes the 'prop drifts to origin on later frames' bug (Animation-mode data
    only had frame 0 set)."""
    csc = de  # placeholder; real csc imported below
    import csc as _csc
    data = dv.get_data(data_id)
    if data.mode == _csc.model.DataMode.Static:
        de.set_data_value(data_id, value)
    else:
        n = max(1, dv.get_animation_size())
        de.set_data_value(data_id, {*range(n)}, value)


def add_prop(ctx, shape="cube", position=None, scale=None, name=None,
             lock=True):
    """Insert a STATIC prop (cube/sphere/cylinder/plane) — a set piece that does
    NOT animate. Position/scale are written across all frames (constant) so it
    stays put, and it is locked (non-selectable) so it can't be posed."""
    csc = ctx.csc
    if shape not in _PART_PATHS:
        raise ValueError("shape must be one of %s" % sorted(_PART_PATHS))
    position = position or [0.0, 0.0, 0.0]
    scale = scale or [1.0, 1.0, 1.0]
    result = {}

    def mod(model, update, scene_updater):
        oid = csc.parts.Buffer.get().insert_object_by_path(
            _PART_PATHS[shape], update.root().group_id(), model,
            ctx.scene.assets_manager())
        scene_updater.generate_update()
        result["id"] = oid

    ctx.scene.modify_update("MCP: add prop", mod)
    oid = result["id"]
    bv = ctx.bv()
    dv = ctx.dv()
    tr = bv.get_behaviour_by_name(oid, "Transform")
    lp = bv.get_behaviour_data(tr, "local_position")
    ls = bv.get_behaviour_data(tr, "local_scale")
    basic = bv.get_behaviour_by_name(oid, "Basic")

    def mod2(model, update, scene_updater):
        de = model.data_editor()
        _write_constant(de, dv, lp, [float(v) for v in position])
        _write_constant(de, dv, ls, [float(v) for v in scale])
        if lock:
            try:
                sel = bv.get_behaviour_data(basic, "selectable")
                if not sel.is_null():
                    _write_constant(de, dv, sel, False)
            except Exception:
                pass
        scene_updater.run_update({lp, ls}, 0)
        if name:
            model.set_object_name(oid, name)

    ctx.scene.modify_update("MCP: place prop", mod2)
    return {"id": oid.to_string(),
            "name": name or ctx.mv().get_object_name(oid),
            "shape": shape, "position": position, "scale": scale,
            "static": True, "locked": lock}


def add_chair(ctx, seat_z=42.0, seat_top_y=45.0, seat_w=40.0, seat_d=34.0,
              back=True, name="Chair"):
    """Assemble a simple STATIC chair (seat + 4 legs + optional backrest) from
    prop cubes, centered at X=0, Z=seat_z, seat surface at Y=seat_top_y. Returns
    the part names. Seat opening faces -Z (backrest at +Z)."""
    hw, hd = seat_w / 2.0, seat_d / 2.0
    base = 80.0  # cube part base size
    parts = []
    # seat (thin slab, top at seat_top_y)
    parts.append(add_prop(ctx, "cube",
                          [0.0, seat_top_y - 2.5, seat_z],
                          [seat_w / base, 5.0 / base, seat_d / base],
                          name="%s_Seat" % name))
    # 4 legs (from floor to just under the seat)
    leg_h = seat_top_y - 5.0
    for lx in (hw - 4, -(hw - 4)):
        for lz in (seat_z - hd + 4, seat_z + hd - 4):
            parts.append(add_prop(ctx, "cube",
                                  [lx, leg_h / 2.0, lz],
                                  [5.0 / base, leg_h / base, 5.0 / base],
                                  name="%s_Leg" % name))
    # backrest at the +Z (back) edge, rising above the seat
    if back:
        parts.append(add_prop(ctx, "cube",
                              [0.0, seat_top_y + 20.0, seat_z + hd - 2],
                              [seat_w / base, 40.0 / base, 4.0 / base],
                              name="%s_Back" % name))
    return {"chair": name, "parts": [p["name"] for p in parts],
            "seat_center": [0.0, seat_top_y, seat_z]}


def set_frame(ctx, frame):
    ctx.scene.set_current_frame(int(frame))
    return {"current_frame": ctx.scene.get_current_frame()}


def set_clip_length(ctx, frames):
    """Extend/shrink the clip to `frames` frames (0 .. frames-1).

    Canonical approach: place a section on the default layer at the last frame,
    then fit the animation size by layers.
    """
    csc = ctx.csc
    last = int(frames) - 1

    def mod(model, update, scene_updater):
        le = model.layers_editor()
        default_layer = ctx.lv().default_layer_id()
        le.set_section(csc.layers.layer.Section(), last, default_layer)
        model.fit_animation_size_by_layers()
        scene_updater.generate_update()

    ctx.scene.modify_update("MCP: set clip length", mod)
    return {"animation_frames": ctx.dv().get_animation_size()}


OPS = {
    "scene.info": scene_info,
    "scene.new": scene_new,
    "scene.open": scene_open,
    "scene.save": scene_save,
    "scene.close_tab": scene_close_tab,
    "scene.close_others": scene_close_others,
    "scene.switch_tab": scene_switch_tab,
    "scene.set_frame": set_frame,
    "scene.set_clip_length": set_clip_length,
    "scene.add_prop": add_prop,
    "scene.add_chair": add_chair,
}
