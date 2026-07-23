"""Object listing, hierarchy, selection and deletion."""

from . import to_jsonable, resolve_objects, behaviour_names_of, get_parent, obj_name


def objects_list(ctx, name_re=None, behaviour=None, limit=200, with_behaviours=False):
    mv = ctx.mv()
    objs = resolve_objects(ctx, name_re=name_re, behaviour=behaviour, limit=limit)
    out = []
    for o in objs:
        item = {
            "id": o.to_string(),
            "name": mv.get_object_name(o),
            "type": mv.get_object_type_name(o),
        }
        if with_behaviours:
            item["behaviours"] = behaviour_names_of(ctx, o)
        out.append(item)
    return {"count": len(out), "objects": out}


def behaviour_summary(ctx):
    """Histogram of behaviour types across the scene: {behaviour_name: count}."""
    bv = ctx.bv()
    mv = ctx.mv()
    hist = {}
    for o in mv.get_objects():
        for name in behaviour_names_of(ctx, o):
            hist[name] = hist.get(name, 0) + 1
    return dict(sorted(hist.items(), key=lambda kv: -kv[1]))


def objects_hierarchy(ctx, behaviour=None, max_depth=100):
    """Parent/child tree built from Basic.parent links.

    behaviour: e.g. 'Joint' to restrict to the skeleton.
    """
    mv = ctx.mv()
    objs = resolve_objects(ctx, behaviour=behaviour)
    ids = {o.to_string(): o for o in objs}
    children = {}
    roots = []
    for o in objs:
        p = get_parent(ctx, o)
        if p is not None and p.to_string() in ids:
            children.setdefault(p.to_string(), []).append(o)
        else:
            roots.append(o)

    def build(o, depth):
        node = {"name": mv.get_object_name(o), "id": o.to_string()}
        if depth < max_depth:
            kids = children.get(o.to_string(), [])
            if kids:
                node["children"] = [build(k, depth + 1) for k in kids]
        return node

    return {"roots": [build(r, 0) for r in roots], "total": len(objs)}


def selection_get(ctx):
    mv = ctx.mv()
    out = []
    sel = ctx.scene.selector().selected()
    for i in sel.ids:
        try:
            if isinstance(i, ctx.csc.model.ObjectId):
                out.append({"id": i.to_string(), "name": mv.get_object_name(i)})
        except Exception:
            pass
    return {"count": len(out), "objects": out}


def selection_set(ctx, names=None, ids=None, name_re=None, behaviour=None,
                  mode="set"):
    csc = ctx.csc
    objs = resolve_objects(ctx, names=names, ids=ids, name_re=name_re,
                           behaviour=behaviour)
    selector = ctx.scene.selector()
    id_set = set(objs)
    if mode == "add":
        try:
            for i in selector.selected().ids:
                if isinstance(i, csc.model.ObjectId):
                    id_set.add(i)
        except Exception:
            pass
    try:
        selector.select(id_set, csc.domain.SelectorMode.NewSelection)
    except Exception:
        # Older/newer signature fallbacks
        try:
            selector.select(id_set)
        except Exception:
            pivot = next(iter(id_set)) if id_set else csc.model.ObjectId.null()
            selector.select(id_set, pivot)
    return {"selected": [obj_name(ctx, o) for o in objs]}


def selection_clear(ctx):
    csc = ctx.csc
    selector = ctx.scene.selector()
    try:
        selector.select(set(), csc.domain.SelectorMode.NewSelection)
    except Exception:
        selector.select(set())
    return {"selected": []}


def objects_delete(ctx, names=None, ids=None, name_re=None):
    objs = resolve_objects(ctx, names=names, ids=ids, name_re=name_re)
    if not objs:
        return {"deleted": 0}
    deleted_names = [obj_name(ctx, o) for o in objs]

    def mod(model, update, scene_updater):
        model.delete_objects(set(objs))
        scene_updater.generate_update()
        scene_updater.run_update(set(), ctx.scene.get_current_frame())

    ctx.scene.modify_update("MCP: delete objects", mod)
    return {"deleted": len(objs), "names": deleted_names}


OPS = {
    "objects.list": objects_list,
    "objects.behaviour_summary": behaviour_summary,
    "objects.hierarchy": objects_hierarchy,
    "selection.get": selection_get,
    "selection.set": selection_set,
    "selection.clear": selection_clear,
    "objects.delete": objects_delete,
}
