"""Tools Pro: fill the in-between frames of a blocked animation with
spline + kinematics + physics (the block->spline->physics pipeline), so the
motion reads correctly instead of interpolating linearly.

- Spline:     BEZIER on every key section (slow-in / slow-out).
- Kinematics: planted feet -> IK + fulcrum fixation (no foot sliding).
- Physics:    the AttractorTool ("tween machine") nudges the in-between frames
              toward a physically-plausible pose (works on the free license).
"""

from commands.tools_pro import _common as U

_FOOT_HINTS = ("foot", "toe", "ankle", "heel")


def command_name():
    return "Tools Pro.Physics fill in-betweens"


def command_description():
    return ("Spline (BEZIER) + IK/fulcrum on planted feet + physics attractor on "
            "the in-between frames of the current animation.")


def run(scene):
    info = U.op("scene.info")
    last = max(int(info.get("animation_frames", 1)) - 1, 1)

    def do(_ignored=None):
        # foot controllers by name hint
        rig = U.op("rig.bone_map")
        roles = rig.get("roles", {}) or {}
        feet = []
        for r, d in roles.items():
            if any(h in r for h in _FOOT_HINTS):
                ctr = (d.get("controllers") or {})
                mp = ctr.get("MainPoint")
                if mp:
                    feet.append(mp.split(":")[-1])

        # 1) SPLINE: BEZIER across the timeline (sample every few frames so each
        #    real section gets set; interval.set is a no-op where there's no key)
        step = max(1, last // 20)
        for f in range(0, last + 1, step):
            try:
                U.op("interval.set", frame=f, interpolation="BEZIER")
            except Exception:
                pass

        # 2) KINEMATICS: feet -> IK + fulcrum
        if feet:
            for f in range(0, last + 1, step):
                try:
                    U.op("interval.set", frame=f, ik_fk="IK",
                         fixation="fulcrum", object_names=feet)
                except Exception:
                    pass

        # 3) PHYSICS: attractor on the in-between frames
        tweened = 0
        for f in range(1, last, max(1, last // 8)):
            try:
                U.op("ai.physics_tween", frame=f, mode="Interpolation", factor=0.5)
                tweened += 1
            except Exception:
                pass

        U.info("Physics fill",
               "Done.\nSpline: BEZIER across %d frames.\nFeet IK+fulcrum: %s.\n"
               "Physics attractor: %d in-between frames."
               % (last + 1,
                  (", ".join(feet) if feet else "no feet detected"),
                  tweened))

    U.buttons("Physics fill",
              "Apply spline + IK/fulcrum feet + physics attractor to the current "
              "animation (0-%d)?" % last,
              [("Yes, fill", U.guard(do))])
