"""Tools Pro: retarget (transfer) animation from another rig onto the current
character. Pick a source FBX (e.g. a Mixamo animation); it is imported to a
temp tab, bone-mapped, and its motion is applied onto the CURRENT rigged
character by matching bones — by name when the naming matches (Mixamo->Mixamo),
otherwise by canonical role (Mixamo->Cascy/UE). Weights are untouched.
"""

from commands.tools_pro import _common as U


def command_name():
    return "Tools Pro.Retarget animation from FBX"


def command_description():
    return ("Transfer animation from a source FBX (e.g. Mixamo) onto the current "
            "rigged character, matching bones by name or canonical role.")


def _roles_and_bake():
    bm = U.op("rig.bone_map")
    roles = {r: d.get("joint") for r, d in (bm.get("roles", {}) or {}).items()}
    hip = None
    hips = (bm.get("roles", {}) or {}).get("hips")
    if hips and hips.get("world_position"):
        hip = hips["world_position"][1]
    return roles, hip, bm


def run(scene):
    import csc
    # remember the target (current) tab
    tgt_info = U.op("scene.info")
    target_tab = tgt_info.get("name")
    tgt_roles, _tgt_hip, _bm = _roles_and_bake()
    tgt_suffixes = {j.split(":")[-1] for j in tgt_roles.values() if j}

    def on_pick(path):
        if not path:
            return

        def do(_ignored=None):
            # import the source clip into a NEW tab
            src = U.op("fbx.import", path=path, mode="scene", new_scene=True)
            src_roles, src_hip, _sbm = _roles_and_bake()
            bake = U.op("anim.bake")
            src_joints = [{"name": j["name"], "frames": j["frames"]}
                          for j in bake["joints"]]
            src_suffixes = {n.split(":")[-1] for n in src_roles.values() if n}

            # choose match mode by name overlap
            name_overlap = len(src_suffixes & tgt_suffixes)
            mode = "name" if name_overlap >= max(6, len(tgt_suffixes) // 2) else "role"

            # back to the target character and apply
            U.op("scene.switch_tab", name=target_tab)
            U.op("scene.set_clip_length", frames=bake["frame_count"] + 2)
            res = U.op("anim.retarget",
                       source_joints=src_joints, source_roles=src_roles,
                       source_hip_height=src_hip, match=mode)
            # free the temp source tab
            try:
                U.op("scene.close_others", keep=target_tab)
            except Exception:
                pass

            applied = res.get("applied_joints") or res.get("joints") or 0
            lines = ["Retarget done (match by %s)." % res.get("match", mode),
                     "",
                     "Source: %s (%d frames)" % (path.split("/")[-1].split("\\")[-1],
                                                 bake["frame_count"]),
                     "Bones driven: %d" % applied]
            if res.get("match") == "role":
                lines.append("Matched roles: %d" % res.get("matched_roles", 0))
                if res.get("hip_scale"):
                    lines.append("Root scaled x%.3f (hip height)"
                                 % res["hip_scale"])
                if res.get("unmatched_source_roles"):
                    lines.append("Unmatched: %s"
                                 % ", ".join(res["unmatched_source_roles"][:8]))
            U.info("Retarget", "\n".join(lines))

        U.buttons("Retarget animation",
                  "Source:\n%s\n\nTransfer this animation onto the current "
                  "character (%s)?" % (path, target_tab),
                  [("Yes, retarget", U.guard(do))])

    U.pick_open_file("Select source animation .fbx", ["*.fbx"], on_pick)
