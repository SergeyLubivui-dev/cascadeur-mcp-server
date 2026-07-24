"""Shared helpers for the Tools Pro command panel.

The Tools Pro commands run INSIDE Cascadeur and reuse the exact same operation
handlers as the MCP bridge (commands.mcp_bridge) — in-process, no TCP. So one
implementation powers both the external automation and the user's in-app panel.
"""

import csc


def get_ctx():
    """Build a bridge Ctx bound to the CURRENT tab's domain scene."""
    from commands.mcp_bridge import _impl
    app = csc.app.get_application()
    dscene = app.get_scene_manager().current_scene().domain_scene()
    return _impl.Ctx(dscene)


def op(name, **args):
    """Run a bridge op by name (e.g. 'rig.bone_map', 'anim.bake') on the current
    scene and return its result. Same registry the MCP bridge dispatches."""
    from commands.mcp_bridge import _impl
    registry, errors = _impl._load_registry()
    if name not in registry:
        raise KeyError("op '%s' not available (load errors: %s)"
                       % (name, list(errors)))
    return registry[name](get_ctx(), **args)


def info(title, message):
    csc.view.DialogManager.instance().show_info(str(title), str(message))


def buttons(title, message, items):
    """Show a window of action buttons. items: [(label, callback), ...]."""
    btns = [csc.view.DialogButton(str(lbl), cb) for lbl, cb in items]
    btns.append(csc.view.DialogButton(csc.view.StandardButton.Cancel))
    csc.view.DialogManager.instance().show_buttons_dialog(str(title),
                                                          str(message), btns)


def inputs(title, fields, fills, callback):
    """Show a multi-field input window. fields/fills are equal-length lists;
    callback(values_list) fires on OK."""
    csc.view.DialogManager.instance().show_inputs_dialog(
        str(title), list(fields), list(fills), len(fields), callback)


def pick_open_file(title, filters, handler):
    """File-open dialog; handler(path) fires with the chosen path."""
    fdm = csc.app.get_application().get_file_dialog_manager()
    fdm.show_open_file_dialog(str(title), "", list(filters), handler)


def pick_save_file(title, default_path, filters, handler):
    fdm = csc.app.get_application().get_file_dialog_manager()
    fdm.show_save_file_dialog(str(title), str(default_path), list(filters), handler)


def guard(fn, err_title="Tools Pro error"):
    """Wrap a callback so any exception surfaces as an info dialog instead of
    silently destabilizing Cascadeur's main thread."""
    def wrapped(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:
            import traceback
            info(err_title, "%s\n\n%s" % (e, traceback.format_exc()[-800:]))
    return wrapped
