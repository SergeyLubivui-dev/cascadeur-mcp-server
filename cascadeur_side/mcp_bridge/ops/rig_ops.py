"""Rig inspection and rigging workflow: joints, controllers, rig mode, quick rig."""

from . import to_jsonable, resolve_objects, behaviour_names_of, get_parent, obj_name


def rig_info(ctx):
    """Overview of rig-related content: joints, rig objects, controller points."""
    bv = ctx.bv()
    mv = ctx.mv()

    joints = bv.get_behaviours("Joint")
    info = {
        "joint_count": len(joints),
        "rig_infos": [],
        "point_controllers": 0,
        "boxes": 0,
    }
    try:
        for ri in bv.get_behaviours("RigInfo"):
            objs = bv.get_behaviour_objects_range(ri, "rig_objects")
            info["rig_infos"].append({
                "owner": obj_name(ctx, bv.get_behaviour_owner(ri)),
                "rig_object_count": len(objs),
            })
    except Exception:
        pass
    for beh_name, key in (("Point", "point_controllers"), ("Box", "boxes")):
        try:
            info[key] = len(bv.get_behaviours(beh_name))
        except Exception:
            pass
    return info


def rig_joints(ctx, frame=None, name_re=None, limit=500):
    """Skeleton listing: joint name, parent, world position at frame."""
    bv = ctx.bv()
    dv = ctx.dv()
    mv = ctx.mv()
    if frame is None:
        frame = ctx.scene.get_current_frame()
    frame = int(frame)

    joints = []
    joint_ids = set()
    for bh in bv.get_behaviours("Joint"):
        joint_ids.add(bv.get_behaviour_owner(bh).to_string())

    objs = resolve_objects(ctx, name_re=name_re, behaviour="Joint", limit=limit)
    for o in objs:
        item = {"name": mv.get_object_name(o), "id": o.to_string()}
        p = get_parent(ctx, o)
        if p is not None:
            item["parent"] = mv.get_object_name(p)
            item["parent_is_joint"] = p.to_string() in joint_ids
        try:
            beh = bv.get_behaviour_by_name(o, "Joint")
            gm = bv.get_behaviour_data(beh, "global_matrix")
            m = dv.get_data_value(gm, frame)
            item["world_position"] = to_jsonable(m[:3, 3])
        except Exception:
            pass
        joints.append(item)
    return {"frame": frame, "count": len(joints), "joints": joints}


_RIG_COLOR = [0.0, 0.5, 0.0]


def _enter_rig_mode(ctx):
    """Enter rig mode; if the scene has no RigInfo yet, create one covering all
    joints first (mirrors rig_mode.on.run_after_import, without dialogs)."""
    import rig_mode.on as rm_on
    import rig_mode.camera_context as cc

    scene = ctx.scene
    bv = ctx.bv()
    if bv.get_behaviours("RigInfo"):
        rm_on.run_raw(scene, _RIG_COLOR)
        return {"rig_mode": "on", "rig_info": "existing"}

    joints = [bv.get_behaviour_owner(bh) for bh in bv.get_behaviours("Joint")]
    undo_context = cc.Camera_context()
    redo_context = cc.Camera_context()

    def mod(model, update, sc_updater, session):
        be = model.behaviour_editor()
        o_id = update.root().create_object("Rig info").object_id()
        rig_info_id = be.add_behaviour(o_id, "RigInfo")
        be.set_behaviour_model_objects_to_range(rig_info_id, "related_joints",
                                                joints)
        sc_updater.generate_update()
        session.take_selector().select({o_id}, o_id)
        rm_on.on(model, update, sc_updater, session, _RIG_COLOR, None, o_id,
                 undo_context, redo_context)

    scene.modify_update_with_session("Rig mode on", mod)
    return {"rig_mode": "on", "rig_info": "created", "joints": len(joints)}


def rig_mode(ctx, on=True, keep_changes=True):
    """Enter or leave rig mode using Cascadeur's bundled scripts."""
    if on:
        return _enter_rig_mode(ctx)
    else:
        import rig_mode.off as rm_off
        rm_off.run(ctx.scene, bool(keep_changes))
        return {"rig_mode": "off"}


def _templates_dir(ctx):
    import os
    import sys
    exe_dir = os.path.dirname(sys.executable)
    for base in (exe_dir, os.path.dirname(exe_dir)):
        d = os.path.join(base, "resources", "autorig_templates")
        if os.path.isdir(d):
            return d
    raise RuntimeError("autorig_templates directory not found")


def qrt_templates(ctx):
    """List available quick-rig templates (.qrigcasc)."""
    import os
    d = _templates_dir(ctx)
    return {"dir": d,
            "templates": sorted(os.path.splitext(f)[0]
                                for f in os.listdir(d) if f.endswith(".qrigcasc"))}


def quick_rig(ctx, template="Mixamo_Namespace_Template_New", autoposing=True,
              open_tool=True):
    """Create a full character rig from a quick-rig template.

    template: name from rig.qrt_templates (e.g. 'Mixamo_Namespace_Template_New',
    'Mixamo_No_Namespace_Template_New', 'UE5', 'CC3_char', 'standard') or an
    absolute path to a .qrigcasc file. The skeleton must already be imported.

    open_tool: when False, do NOT open the interactive Quick Rigging panel — the
    rig is still built from the template, but Cascadeur won't pop the "Rig
    elements have been added / Generate rig" helper dialog that blocks a
    one-click flow. Use False for the in-app Tools Pro command.
    """
    import os
    if os.path.isabs(template) and os.path.isfile(template):
        path = template
    else:
        d = _templates_dir(ctx)
        path = os.path.join(d, template + ".qrigcasc")
        if not os.path.isfile(path):
            available = sorted(os.path.splitext(f)[0] for f in os.listdir(d)
                               if f.endswith(".qrigcasc"))
            raise FileNotFoundError(
                "Template %r not found. Available: %s" % (template, available))

    joints_before = len(ctx.bv().get_behaviours("Joint"))
    if joints_before == 0:
        raise RuntimeError("No joints in the scene; import a skeleton first")

    steps = []

    # 1. Rig mode ON (creates Rig info over all joints if needed). QRT methods
    #    crash Cascadeur when called outside rig mode.
    steps.append(("rig_mode_on", _enter_rig_mode(ctx)))

    # 2. Quick Rigging Tool: load template and build proto rig elements.
    tool = ctx.app.get_tools_manager().get_tool("RiggingToolWindowTool")
    editor = tool.editor(ctx.app_scene())
    if open_tool:
        editor.open_quick_rigging_tool()
    try:
        editor.set_is_create_autoposing(bool(autoposing))
    except Exception:
        pass
    editor.load_template_by_fileName(path.replace("\\", "/"))
    steps.append(("template_loaded", os.path.basename(path)))
    editor.generate_rig_elements()
    steps.append(("rig_elements_generated", True))

    # 3. Rig mode OFF -> generates the final rig (controllers, IK/FK points).
    import rig_mode.off as rm_off
    rm_off.run(ctx.scene, True)
    steps.append(("rig_mode_off", True))

    return {
        "template": os.path.basename(path),
        "steps": steps,
        "rig": rig_info(ctx),
    }


def qrt_open(ctx):
    """Open the Quick Rigging Tool window for manual template mapping."""
    tool = ctx.app.get_tools_manager().get_tool("RiggingToolWindowTool")
    tool.editor(ctx.app_scene()).open_quick_rigging_tool()
    return {"opened": True}


def qrt_introspect(ctx):
    """Debug: inspect RiggingToolWindowTool editor and csc.rig contents."""
    tool = ctx.app.get_tools_manager().get_tool("RiggingToolWindowTool")
    editor = tool.editor(ctx.app_scene())
    rig_mod = getattr(ctx.csc, "rig", None)
    return {
        "editor": [a for a in dir(editor) if not a.startswith("_")],
        "csc.rig": [a for a in dir(rig_mod) if not a.startswith("_")] if rig_mod else None,
    }


OPS = {
    "rig.info": rig_info,
    "rig.joints": rig_joints,
    "rig.mode": rig_mode,
    "rig.quick_rig": quick_rig,
    "rig.qrt_templates": qrt_templates,
    "rig.qrt_open": qrt_open,
    "rig.qrt_introspect": qrt_introspect,
}
