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
            # build the Quick Rig (non-interactive so it doesn't stop on the
            # "Generate rig" helper dialog)
            rig = U.op("rig.quick_rig", template=_TEMPLATES["mixamo"],
                       autoposing=True, open_tool=False)
            rig = rig.get("rig", rig) if isinstance(rig, dict) else rig
            joints = rig.get("joint_count", "?") if isinstance(rig, dict) else "?"
            ctrls = rig.get("point_controllers", "?") if isinstance(rig, dict) else "?"
            # concise summary — no raw dict dump
            lines = ["Character imported and rigged — ready to animate.",
                     "",
                     "Bones: %s joints, %s controllers" % (joints, ctrls),
                     "Roles mapped: %d" % len(roles),
                     "Fingers: %s" % ("yes" if fingers else "none")]
            if unmapped:
                lines.append("Unmapped: %s" % ", ".join(unmapped[:10]))
            U.info("Rig ready", "\n".join(lines))

        # confirm the template first (keeps it one obvious choice for now)
        U.buttons("Rig Mixamo FBX",
                  "File:\n%s\n\nAuto-map bones and build a Mixamo Quick Rig?"
                  % path,
                  [("Yes, rig it", U.guard(do))])

    U.pick_open_file("Select a Mixamo .fbx", ["*.fbx"], on_pick)
