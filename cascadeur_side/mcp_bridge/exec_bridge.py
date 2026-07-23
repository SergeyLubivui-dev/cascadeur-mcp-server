"""Stable entry point for the cascadeur-mcp-pro bridge.

Triggered with: cascadeur.exe --run-script commands.mcp_bridge.exec_bridge

All real logic lives in ``_impl.py`` which is re-loaded on every trigger, so the
bridge can be updated on disk without restarting Cascadeur. Keep THIS file
minimal and stable: it may stay cached in Cascadeur's interpreter forever.
"""


def command_name():
    return "MCP.Bridge Exec"


def command_description():
    return "Bridge session used by the cascadeur-mcp-pro server"


def run(scene):
    import importlib
    import traceback
    try:
        from commands.mcp_bridge import _impl
        importlib.reload(_impl)
        _impl.serve(scene)
    except Exception:
        try:
            scene.error("MCP bridge loader failed:\n" + traceback.format_exc())
        except Exception:
            pass
