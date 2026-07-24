"""Tools Pro: export baked animation to Unity as SEPARATE clips.

Unity treats each animation-only FBX named "<Model>@<clip>.fbx" as one clip on
the shared skeleton (the classic Mixamo/Unity workflow). So instead of one long
merged clip, you get walk / sit / idle as distinct clips Unity imports cleanly.

Clips are entered as "name:start-end, name:start-end". Empty -> one clip over
the whole timeline. Uses our free bake->FBX writer (no paid FBX-export license).
"""

import os
from commands.tools_pro import _common as U
from commands.tools_pro import fbx_writer


def command_name():
    return "Tools Pro.Export to Unity"


def command_description():
    return ("Bake and export animation clips as separate Unity-ready FBX files "
            "(Model@clip.fbx) — correct clip sectioning, not one merged clip.")


def _parse_clips(text, last_frame):
    """'walk:0-30, sit:30-70' -> [('walk',0,30), ('sit',30,70)].
    Blank -> one 'take' clip over the whole timeline."""
    text = (text or "").strip()
    if not text:
        return [("take", 0, last_frame)]
    clips = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, rng = chunk.partition(":")
        name = name.strip() or "clip"
        a, _, b = rng.partition("-")
        try:
            s = int(a.strip())
            e = int(b.strip()) if b.strip() else last_frame
        except ValueError:
            raise ValueError("bad clip range in %r (use name:start-end)" % chunk)
        clips.append((name, s, e))
    return clips


def run(scene):
    # discover the timeline length to seed the default clip field
    info = U.op("scene.info")
    last = max(int(info.get("animation_frames", 1)) - 1, 1)

    def on_inputs(values):
        base = (values[0] or "").strip()
        clips_s = values[1] if len(values) > 1 else ""
        if not base:
            U.info("Export", "No output path given.")
            return
        base = base.replace("\\", "/")
        if base.lower().endswith(".fbx"):
            base = base[:-4]
        os.makedirs(os.path.dirname(base) or ".", exist_ok=True)

        clips = _parse_clips(clips_s, last)
        written = []
        for name, s, e in clips:
            bake = U.op("anim.bake", frame_start=s, frame_end=e + 1)
            if bake.get("joint_count", 0) == 0:
                continue
            safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
            path = "%s@%s.fbx" % (base, safe)
            fbx_writer.write_fbx_ascii(bake, path)
            written.append("%s  (%d-%d, %d jts)"
                           % (os.path.basename(path), s, e, bake["joint_count"]))

        U.info("Export to Unity",
               "Wrote %d clip file(s) next to:\n%s\n\n%s\n\n"
               "Drop them into Unity's Assets alongside your model; each imports "
               "as a clip on the shared skeleton."
               % (len(written), base, "\n".join(written) or "(nothing)"))

    U.inputs("Export to Unity (clips)",
             ["Output base path (no extension)",
              "Clips  name:start-end, ...  (blank = whole timeline)"],
             ["D:/export/character",
              "walk:0-%d" % last],
             on_inputs)
