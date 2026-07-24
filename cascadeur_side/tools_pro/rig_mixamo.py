"""Tools Pro: import a Mixamo (or other) FBX, auto-map its bones to canonical
roles, and build a Quick Rig so it is immediately animatable.

Ready-algorithm path (fast, deterministic): the bone auto-mapping heuristic
handles Mixamo / UE / CC / Cascy naming. The result dialog lists any UNMAPPED
bones so you can catch a weird skeleton before rigging (AI-assist fallback:
ask Claude via MCP to resolve odd mappings).
"""

from commands.tools_pro import _common as U

# Quick Rig templates by convention. Mixamo characters use the Mixamo template.
_TEMPLATES = {
    "mixamo": "Mixamo_Namespace_Template_New",
}


def command_name():
    return "Tools Pro.Rig Mixamo FBX"


def command_description():
    return ("Import a Mixamo .fbx, auto-map bones to canonical roles and build a "
            "Quick Rig (AutoPosing on) so it can be animated.")


def run(scene):
    def on_pick(path):
        if not path:
            return

        def do(_ignored=None):
            # import the model into a fresh scene
            U.op("fbx.import", path=path, mode="model", new_scene=True)
            # auto bone-map (heuristic role classification)
            bm = U.op("rig.bone_map")
            roles = bm.get("roles", {}) or {}
            unmapped = bm.get("unmapped", []) or []
            fingers = bm.get("finger_summary") or bm.get("fingers")
            # build the Quick Rig
            rig = U.op("rig.quick_rig",
                       template=_TEMPLATES["mixamo"], autoposing=True)
            msg = ("Imported + rigged.\n\n"
                   "Mapped roles: %d\n"
                   "Fingers: %s\n"
                   "Unmapped bones: %s\n\n"
                   "Rig: %s\n\nThe character is ready to animate."
                   % (len(roles),
                      "yes" if fingers else "none",
                      (", ".join(unmapped[:12]) if unmapped else "none"),
                      rig.get("status", rig)))
            U.info("Rig ready", msg)

        # confirm the template first (keeps it one obvious choice for now)
        U.buttons("Rig Mixamo FBX",
                  "File:\n%s\n\nAuto-map bones and build a Mixamo Quick Rig?"
                  % path,
                  [("Yes, rig it", U.guard(do))])

    U.pick_open_file("Select a Mixamo .fbx", ["*.fbx"], on_pick)
