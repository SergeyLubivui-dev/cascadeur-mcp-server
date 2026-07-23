"""FBX import/export via the FbxSceneLoader tool."""

_IMPORT_MODES = {
    "scene": "import_scene",
    "model": "import_model",
    "model_to_selected": "add_model_to_selected",
    "add_model": "add_model",
    "animation": "import_animation",
    "animation_to_selected_objects": "import_animation_to_selected_objects",
    "animation_to_selected_frames": "import_animation_to_selected_frames",
}

_EXPORT_MODES = {
    "all": "export_all_objects",
    "model": "export_model",
    "joints": "export_joints",
    "selected": "export_scene_selected",
}


def _loader(ctx):
    tool = ctx.app.get_tools_manager().get_tool("FbxSceneLoader")
    return tool.get_fbx_loader(ctx.app_scene())


def _apply_settings(ctx, loader, ascii=None, up_axis=None, bake_animation=None,
                    apply_euler_filter=None):
    if all(v is None for v in (ascii, up_axis, bake_animation, apply_euler_filter)):
        return
    fbx = ctx.csc.fbx
    settings = fbx.FbxSettings()
    if ascii is not None:
        settings.mode = fbx.FbxSettingsMode.Ascii if ascii else fbx.FbxSettingsMode.Binary
    if up_axis is not None:
        settings.up_axis = getattr(fbx.FbxSettingsAxis, up_axis.upper())
    if bake_animation is not None:
        settings.bake_animation = bool(bake_animation)
    if apply_euler_filter is not None:
        settings.apply_euler_filter = bool(apply_euler_filter)
    loader.set_settings(settings)


def fbx_import(ctx, path, mode="model", new_scene=False):
    import os
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    if mode not in _IMPORT_MODES:
        raise ValueError("mode must be one of %s" % sorted(_IMPORT_MODES))
    if new_scene:
        sm = ctx.app.get_scene_manager()
        sm.set_current_scene(sm.create_application_scene())
    loader = _loader(ctx)
    getattr(loader, _IMPORT_MODES[mode])(path.replace("\\", "/"))
    return {
        "imported": path,
        "mode": mode,
        "object_count": len(ctx.app_scene().domain_scene().model_viewer().get_objects()),
    }


def fbx_export(ctx, path, what="all", ascii=None, up_axis=None,
               bake_animation=None, apply_euler_filter=None):
    import os
    import time
    if what not in _EXPORT_MODES:
        raise ValueError("what must be one of %s" % sorted(_EXPORT_MODES))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    loader = _loader(ctx)
    _apply_settings(ctx, loader, ascii, up_axis, bake_animation, apply_euler_filter)
    getattr(loader, _EXPORT_MODES[what])(path.replace("\\", "/"))
    for _ in range(10):
        if os.path.isfile(path):
            break
        time.sleep(0.1)
    if not os.path.isfile(path):
        raise RuntimeError(
            "FBX export produced no file. NOTE: the free/trial Cascadeur "
            "license only supports the .casc format — FBX export requires a "
            "Pro/Business license (this appears in Cascadeur's event log). "
            "Use scene.save to write a .casc instead.")
    return {"exported": path, "what": what, "size": os.path.getsize(path)}


OPS = {
    "fbx.import": fbx_import,
    "fbx.export": fbx_export,
}
