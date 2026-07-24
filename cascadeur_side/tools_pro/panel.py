"""Tools Pro launcher — opens the custom-styled WEB panel in your browser.

The web panel (a local page served by the MCP project) is fully styled and
richer than Cascadeur's built-in dialogs, and drives Cascadeur through the same
bridge. This command starts that local server (if not already running) and
opens it in the default browser.

Appears in Cascadeur's command list as "Tools Pro.Open Panel". The individual
"Tools Pro.*" commands still work as in-app dialogs if you prefer those.
"""

import os
import subprocess
import sys

from commands.tools_pro import _common as U

try:
    from commands.tools_pro import _env  # written by install_bridge.py
    REPO_ROOT = getattr(_env, "REPO_ROOT", "")
    VENV_PY = getattr(_env, "VENV_PY", "")
    PANEL_PORT = getattr(_env, "PANEL_PORT", 8765)
except Exception:
    REPO_ROOT, VENV_PY, PANEL_PORT = "", "", 8765


def command_name():
    return "Tools Pro.Open Panel"


def command_description():
    return ("Open the custom-styled Tools Pro web panel (rig, retarget, physics "
            "fill, Unity export) in your browser.")


def run(scene):
    port = int(PANEL_PORT or 8765)
    script = os.path.join(REPO_ROOT, "run_panel.py") if REPO_ROOT else ""
    if not script or not os.path.isfile(script):
        U.info("Tools Pro",
               "Web panel launcher not found.\nRun it manually:\n"
               "  python run_panel.py\n(in the MCP project folder).")
        return

    # run_panel.py opens the panel as a frameless app-window; if the server is
    # already up it just re-opens the window. Spawn it detached so it outlives
    # this command with no console window.
    py = VENV_PY if (VENV_PY and os.path.isfile(VENV_PY)) else sys.executable
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) \
            | getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        subprocess.Popen([py, script, "--port", str(port)],
                         cwd=REPO_ROOT, creationflags=flags, close_fds=True)
        U.info("Tools Pro", "Opening the Tools Pro panel window…\n"
               "(keep Cascadeur open — the panel drives it via the bridge.)")
    except Exception as e:
        U.info("Tools Pro", "Could not start the panel:\n%s\n\n"
               "Run manually: python run_panel.py" % e)
