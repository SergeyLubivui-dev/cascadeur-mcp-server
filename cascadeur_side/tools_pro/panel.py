"""Tools Pro launcher — a button window that opens the other actions.

Appears in Cascadeur's command list as "Tools Pro.Open Panel" (the dot makes a
"Tools Pro" submenu). Assign a hotkey to it in Settings for one-key access.
"""

from commands.tools_pro import _common as U


def command_name():
    return "Tools Pro.Open Panel"


def command_description():
    return ("MCP Tools Pro: rig a Mixamo model, physics-fill in-betweens, and "
            "export Unity-ready animation clips.")


def run(scene):
    from commands.tools_pro import rig_mixamo, export_unity, physics_fill

    def cleanup():
        r = U.op("scene.close_others")
        U.info("Cleanup", "Closed %d tab(s), %d remaining."
               % (r.get("closed_count", 0), r.get("remaining", 1)))

    U.buttons("Tools Pro", "Choose an action:", [
        ("Rig Mixamo FBX  (import + auto bone-map + Quick Rig)",
         U.guard(lambda: rig_mixamo.run(scene))),
        ("Physics fill  (spline + IK/fulcrum feet + attractor)",
         U.guard(lambda: physics_fill.run(scene))),
        ("Export to Unity  (baked clips -> Model@clip.fbx)",
         U.guard(lambda: export_unity.run(scene))),
        ("Cleanup scene tabs  (free memory)",
         U.guard(cleanup)),
    ])
