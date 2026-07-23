"""Writers for baked skeletal animation: ASCII FBX 7.3 and BVH.

Input `bake` format (from bridge op anim.bake):
{
  "frame_count": N, "fps": 30,
  "joints": [{"name": str, "parent": str|None,
              "frames": [[tx,ty,tz, rx,ry,rz], ...]}, ...]   # euler XYZ deg
}

The FBX contains a LimbNode skeleton with baked Lcl Translation/Rotation
curves — enough for Unity/Blender/Cascadeur to read the animation and retarget
by joint names (classic Mixamo animation-clip workflow).
"""

from __future__ import annotations

KTIME_PER_SEC = 46186158000


def _fmt(v: float) -> str:
    return ("%.6f" % v).rstrip("0").rstrip(".")


def write_fbx_ascii(bake: dict, path: str) -> None:
    joints = bake["joints"]
    n_frames = bake["frame_count"]
    fps = bake.get("fps", 30)
    ktime_frame = KTIME_PER_SEC // fps
    stop_time = (max(n_frames - 1, 1)) * ktime_frame

    next_id = [1000000000]

    def new_id() -> int:
        next_id[0] += 1
        return next_id[0]

    model_ids = {j["name"]: new_id() for j in joints}
    stack_id, layer_id = new_id(), new_id()

    lines: list[str] = []
    out = lines.append

    out("; FBX 7.3.0 project file")
    out("; Exported by cascadeur-mcp-pro (baked skeletal animation)")
    out("FBXHeaderExtension:  {")
    out("\tFBXHeaderVersion: 1003")
    out("\tFBXVersion: 7300")
    out('\tCreator: "cascadeur-mcp-pro"')
    out("}")
    out("GlobalSettings:  {")
    out("\tVersion: 1000")
    out("\tProperties70:  {")
    out('\t\tP: "UpAxis", "int", "Integer", "",1')
    out('\t\tP: "UpAxisSign", "int", "Integer", "",1')
    out('\t\tP: "FrontAxis", "int", "Integer", "",2')
    out('\t\tP: "FrontAxisSign", "int", "Integer", "",1')
    out('\t\tP: "CoordAxis", "int", "Integer", "",0')
    out('\t\tP: "CoordAxisSign", "int", "Integer", "",1')
    out('\t\tP: "UnitScaleFactor", "double", "Number", "",1')
    out('\t\tP: "OriginalUnitScaleFactor", "double", "Number", "",1')
    out('\t\tP: "TimeMode", "enum", "", "",6')
    out('\t\tP: "TimeSpanStart", "KTime", "Time", "",0')
    out('\t\tP: "TimeSpanStop", "KTime", "Time", "",%d' % stop_time)
    out('\t\tP: "CustomFrameRate", "double", "Number", "",%d' % fps)
    out("\t}")
    out("}")
    out("Documents:  {")
    out("\tCount: 1")
    out('\tDocument: %d, "", "Scene" {' % new_id())
    out("\t\tProperties70:  {")
    out('\t\t\tP: "SourceObject", "object", "", ""')
    out('\t\t\tP: "ActiveAnimStackName", "KString", "", "", "Take 001"')
    out("\t\t}")
    out("\t\tRootNode: 0")
    out("\t}")
    out("}")
    out("References:  {")
    out("}")

    n_curve_nodes = len(joints) * 2
    n_curves = len(joints) * 6
    out("Definitions:  {")
    out("\tVersion: 100")
    out("\tCount: %d" % (len(joints) + 2 + n_curve_nodes + n_curves))
    out('\tObjectType: "Model" {\n\t\tCount: %d\n\t}' % len(joints))
    out('\tObjectType: "AnimationStack" {\n\t\tCount: 1\n\t}')
    out('\tObjectType: "AnimationLayer" {\n\t\tCount: 1\n\t}')
    out('\tObjectType: "AnimationCurveNode" {\n\t\tCount: %d\n\t}' % n_curve_nodes)
    out('\tObjectType: "AnimationCurve" {\n\t\tCount: %d\n\t}' % n_curves)
    out("}")

    out("Objects:  {")
    for j in joints:
        f0 = j["frames"][0]
        out('\tModel: %d, "Model::%s", "LimbNode" {' % (model_ids[j["name"]], j["name"]))
        out("\t\tVersion: 232")
        out("\t\tProperties70:  {")
        out('\t\t\tP: "RotationOrder", "enum", "", "",0')
        out('\t\t\tP: "RotationActive", "bool", "", "",1')
        out('\t\t\tP: "Lcl Translation", "Lcl Translation", "", "A",%s,%s,%s'
            % (_fmt(f0[0]), _fmt(f0[1]), _fmt(f0[2])))
        out('\t\t\tP: "Lcl Rotation", "Lcl Rotation", "", "A",%s,%s,%s'
            % (_fmt(f0[3]), _fmt(f0[4]), _fmt(f0[5])))
        out('\t\t\tP: "Lcl Scaling", "Lcl Scaling", "", "A",1,1,1')
        out("\t\t}")
        out("\t\tShading: T")
        out('\t\tCulling: "CullingOff"')
        out("\t}")

    out('\tAnimationStack: %d, "AnimStack::Take 001", "" {' % stack_id)
    out("\t\tProperties70:  {")
    out('\t\t\tP: "LocalStart", "KTime", "Time", "",0')
    out('\t\t\tP: "LocalStop", "KTime", "Time", "",%d' % stop_time)
    out('\t\t\tP: "ReferenceStart", "KTime", "Time", "",0')
    out('\t\t\tP: "ReferenceStop", "KTime", "Time", "",%d' % stop_time)
    out("\t\t}")
    out("\t}")
    out('\tAnimationLayer: %d, "AnimLayer::BaseLayer", "" {' % layer_id)
    out("\t}")

    times = ",".join(str(f * ktime_frame) for f in range(n_frames))
    key_attr_tail = (
        "\t\tKeyAttrFlags: *1 {\n\t\t\ta: 24840\n\t\t}\n"
        "\t\tKeyAttrDataFloat: *4 {\n\t\t\ta: 0,0,218434821,0\n\t\t}\n"
        "\t\tKeyAttrRefCount: *1 {\n\t\t\ta: %d\n\t\t}" % n_frames)

    conn: list[str] = []
    conn.append('\tC: "OO",%d,%d' % (layer_id, stack_id))

    for j in joints:
        name = j["name"]
        mid = model_ids[name]
        if j["parent"] and j["parent"] in model_ids:
            conn.append('\tC: "OO",%d,%d' % (mid, model_ids[j["parent"]]))
        else:
            conn.append('\tC: "OO",%d,0' % mid)

        for prop, base_idx, label in (("Lcl Translation", 0, "T"),
                                      ("Lcl Rotation", 3, "R")):
            cn_id = new_id()
            f0 = j["frames"][0]
            out('\tAnimationCurveNode: %d, "AnimCurveNode::%s", "" {' % (cn_id, label))
            out("\t\tProperties70:  {")
            out('\t\t\tP: "d|X", "Number", "", "A",%s' % _fmt(f0[base_idx]))
            out('\t\t\tP: "d|Y", "Number", "", "A",%s' % _fmt(f0[base_idx + 1]))
            out('\t\t\tP: "d|Z", "Number", "", "A",%s' % _fmt(f0[base_idx + 2]))
            out("\t\t}")
            out("\t}")
            conn.append('\tC: "OO",%d,%d' % (cn_id, layer_id))
            conn.append('\tC: "OP",%d,%d, "%s"' % (cn_id, mid, prop))
            for axis_i, axis in enumerate("XYZ"):
                curve_id = new_id()
                values = ",".join(_fmt(fr[base_idx + axis_i]) for fr in j["frames"])
                out('\tAnimationCurve: %d, "AnimCurve::", "" {' % curve_id)
                out("\t\tDefault: %s" % _fmt(j["frames"][0][base_idx + axis_i]))
                out("\t\tKeyVer: 4008")
                out("\t\tKeyTime: *%d {\n\t\t\ta: %s\n\t\t}" % (n_frames, times))
                out("\t\tKeyValueFloat: *%d {\n\t\t\ta: %s\n\t\t}" % (n_frames, values))
                out(key_attr_tail)
                out("\t}")
                conn.append('\tC: "OP",%d,%d, "d|%s"' % (curve_id, cn_id, axis))

    out("}")
    out("Connections:  {")
    lines.extend(conn)
    out("}")
    out("Takes:  {")
    out('\tCurrent: "Take 001"')
    out('\tTake: "Take 001" {')
    out('\t\tFileName: "Take_001.tak"')
    out("\t\tLocalTime: 0,%d" % stop_time)
    out("\t\tReferenceTime: 0,%d" % stop_time)
    out("\t}")
    out("}")

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def write_bvh(bake: dict, path: str) -> None:
    joints = bake["joints"]
    n_frames = bake["frame_count"]
    fps = bake.get("fps", 30)
    by_name = {j["name"]: j for j in joints}
    children: dict[str | None, list[dict]] = {}
    for j in joints:
        parent = j["parent"] if j["parent"] in by_name else None
        children.setdefault(parent, []).append(j)

    lines: list[str] = ["HIERARCHY"]
    channel_order: list[tuple[dict, bool]] = []  # (joint, is_root)

    def emit(j: dict, depth: int, is_root: bool) -> None:
        indent = "\t" * depth
        f0 = j["frames"][0]
        lines.append("%s%s %s" % (indent, "ROOT" if is_root else "JOINT", j["name"]))
        lines.append(indent + "{")
        lines.append("%s\tOFFSET %s %s %s" % (indent, _fmt(f0[0]), _fmt(f0[1]),
                                              _fmt(f0[2])))
        if is_root:
            lines.append(indent + "\tCHANNELS 6 Xposition Yposition Zposition "
                         "Zrotation Yrotation Xrotation")
        else:
            lines.append(indent + "\tCHANNELS 3 Zrotation Yrotation Xrotation")
        channel_order.append((j, is_root))
        kids = children.get(j["name"], [])
        if kids:
            for k in kids:
                emit(k, depth + 1, False)
        else:
            lines.append(indent + "\tEnd Site")
            lines.append(indent + "\t{")
            lines.append(indent + "\t\tOFFSET 0 0 0")
            lines.append(indent + "\t}")
        lines.append(indent + "}")

    for root in children.get(None, []):
        emit(root, 0, True)

    lines.append("MOTION")
    lines.append("Frames: %d" % n_frames)
    lines.append("Frame Time: %.6f" % (1.0 / fps))
    for f in range(n_frames):
        row: list[str] = []
        for j, is_root in channel_order:
            fr = j["frames"][f]
            if is_root:
                row += [_fmt(fr[0]), _fmt(fr[1]), _fmt(fr[2])]
            row += [_fmt(fr[5]), _fmt(fr[4]), _fmt(fr[3])]
        lines.append(" ".join(row))

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
