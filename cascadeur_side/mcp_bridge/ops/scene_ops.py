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
    "scene.switch_tab": scene_switch_tab,
    "scene.set_frame": set_frame,
    "scene.set_clip_length": set_clip_length,
}
