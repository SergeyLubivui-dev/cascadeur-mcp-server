"""Cascadeur-side bridge for cascadeur-mcp-pro.

Installed as ``<Cascadeur>/resources/scripts/python/commands/mcp_bridge/`` so it can be
triggered with::

    cascadeur.exe --run-script commands.mcp_bridge.exec_bridge

``run(scene)`` executes on Cascadeur's main thread. It connects to the MCP server's
TCP listener (port taken from a temp file), then serves a short session: the server
sends one or more batches of operations, the bridge executes them against the ``csc``
API and replies. The session ends when the server sends ``{"end": true}`` or on
timeout, so the UI is never blocked for long.

Operations are named handlers registered in ``ops`` submodules (hot-reloaded when
their files change), plus a ``python.exec`` escape hatch.
"""

import importlib
import io
import json
import os
import socket
import sys
import tempfile
import traceback
import contextlib

_HEADER = 12
_PORT_FILE = os.path.join(tempfile.gettempdir(), "cascadeur_mcp_pro.json")
# Persistent-session friendly: one trigger can serve a whole build. The serve
# loop blocks Cascadeur's main thread only while waiting for the next batch, so
# keep the idle wait moderate (UI is frozen during that wait) and cap the whole
# session so a stuck client can't freeze the app forever.
_SESSION_TIMEOUT = 300.0   # hard cap on one bridge session, seconds
_RECV_TIMEOUT = 30.0       # max idle wait for the next batch from the server

_OP_MODULES = [
    "commands.mcp_bridge.ops.scene_ops",
    "commands.mcp_bridge.ops.object_ops",
    "commands.mcp_bridge.ops.transform_ops",
    "commands.mcp_bridge.ops.keyframe_ops",
    "commands.mcp_bridge.ops.fbx_ops",
    "commands.mcp_bridge.ops.tool_ops",
    "commands.mcp_bridge.ops.rig_ops",
    "commands.mcp_bridge.ops.anim_ops",
    "commands.mcp_bridge.ops.ai_ops",
    "commands.mcp_bridge.ops.bonemap_ops",
    "commands.mcp_bridge.ops.rigmodel_ops",
]

_module_mtimes = {}


# ---------------------------------------------------------------- framing

def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed")
        buf += chunk
    return buf


def _recv_json(sock):
    length = int(_recv_exact(sock, _HEADER).decode("ascii").strip())
    return json.loads(_recv_exact(sock, length).decode("utf-8"))


def _send_json(sock, obj):
    data = json.dumps(obj, ensure_ascii=False, default=_json_default).encode("utf-8")
    sock.sendall(str(len(data)).ljust(_HEADER).encode("ascii") + data)


def _json_default(obj):
    """Fallback serialisation for csc/numpy objects that leak into results."""
    try:
        import numpy as np
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
    except Exception:
        pass
    for attr in ("to_string",):
        f = getattr(obj, attr, None)
        if callable(f):
            try:
                return f()
            except Exception:
                pass
    if isinstance(obj, (set, frozenset, tuple)):
        return list(obj)
    return repr(obj)


# ---------------------------------------------------------------- op registry

def _load_registry(force_reload=False):
    registry = {}
    errors = {}
    for mod_name in _OP_MODULES:
        try:
            mod = importlib.import_module(mod_name)
            path = getattr(mod, "__file__", None)
            if path and os.path.exists(path):
                mtime = os.path.getmtime(path)
                if force_reload or _module_mtimes.get(mod_name) not in (None, mtime):
                    mod = importlib.reload(mod)
                _module_mtimes[mod_name] = mtime
            registry.update(getattr(mod, "OPS", {}))
        except Exception:
            errors[mod_name] = traceback.format_exc()
    return registry, errors


class Ctx(object):
    """Execution context passed to every op handler.

    ``scene`` always resolves to the CURRENT tab's domain scene, so ops that
    switch or create tabs stay consistent within one session.
    """

    def __init__(self, scene):
        import csc
        self.csc = csc
        self._trigger_scene = scene              # csc.domain.Scene at trigger time
        self.app = csc.app.get_application()

    @property
    def scene(self):
        try:
            return self.app_scene().domain_scene()
        except Exception:
            return self._trigger_scene

    def app_scene(self):
        return self.app.get_scene_manager().current_scene()

    def mv(self):
        return self.scene.model_viewer()

    def bv(self):
        return self.scene.model_viewer().behaviour_viewer()

    def dv(self):
        return self.scene.model_viewer().data_viewer()

    def lv(self):
        return self.scene.layers_viewer()


def _exec_python(ctx, code):
    """python.exec escape hatch: run raw code with csc/scene/app in scope."""
    namespace = {
        "csc": ctx.csc,
        "scene": ctx.scene,
        "app": ctx.app,
        "ctx": ctx,
        "result": None,
    }
    try:
        import pycsc
        namespace["pycsc"] = pycsc
    except Exception:
        pass
    exec(code, namespace)
    return namespace.get("result")


def _run_one(ctx, registry, request):
    op = request.get("op", "")
    args = request.get("args") or {}
    out = io.StringIO()
    resp = {"id": request.get("id")}
    try:
        with contextlib.redirect_stdout(out):
            if op == "python.exec":
                result = _exec_python(ctx, args.get("code", ""))
            elif op == "ops.list":
                result = sorted(registry.keys()) + ["python.exec", "ops.list"]
            elif op in registry:
                result = registry[op](ctx, **args)
            else:
                raise KeyError(
                    "Unknown op %r. Known: %s" % (op, sorted(registry.keys())))
        resp["status"] = "ok"
        resp["result"] = result
    except Exception:
        resp["status"] = "error"
        resp["error"] = traceback.format_exc()
    stdout_text = out.getvalue()
    if stdout_text:
        resp["stdout"] = stdout_text[-20000:]
    return resp


# ---------------------------------------------------------------- entry point

def serve(scene):
    try:
        with open(_PORT_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        port = int(cfg["port"])
    except Exception:
        return  # no server waiting for us

    import time
    started = time.monotonic()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(_RECV_TIMEOUT)
    try:
        sock.connect(("127.0.0.1", port))
        registry, load_errors = _load_registry()
        ctx = Ctx(scene)
        _send_json(sock, {
            "hello": "cascadeur-mcp-pro-bridge",
            "version": 1,
            "python": sys.version,
            "ops": sorted(registry.keys()),
            "load_errors": load_errors,
        })
        while time.monotonic() - started < _SESSION_TIMEOUT:
            msg = _recv_json(sock)
            if msg.get("end"):
                break
            if msg.get("reload"):
                registry, load_errors = _load_registry(force_reload=True)
                _send_json(sock, {"responses": [], "reloaded": True,
                                  "load_errors": load_errors})
                continue
            responses = [_run_one(ctx, registry, r)
                         for r in msg.get("requests", [])]
            _send_json(sock, {"responses": responses})
    except Exception:
        try:
            scene.error("MCP bridge session failed:\n" + traceback.format_exc())
        except Exception:
            pass
    finally:
        try:
            sock.close()
        except Exception:
            pass
