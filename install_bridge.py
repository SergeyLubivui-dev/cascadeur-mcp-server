"""Install (copy) the mcp_bridge command package into Cascadeur's scripts folder.

Usage:  python install_bridge.py [--cascadeur-dir <dir>] [--uninstall]

The target is <Cascadeur>/resources/scripts/python/commands/mcp_bridge.
The Cascadeur directory is auto-detected from a running cascadeur.exe process,
CASCADEUR_EXE_PATH, or the default install location.
"""

import argparse
import os
import shutil
import subprocess
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "cascadeur_side", "mcp_bridge")


def detect_cascadeur_dir() -> str:
    env = os.environ.get("CASCADEUR_EXE_PATH")
    if env and os.path.isfile(env):
        return os.path.dirname(env)
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Process cascadeur -ErrorAction SilentlyContinue | "
             "Select-Object -First 1).Path"],
            capture_output=True, text=True, timeout=15)
        path = (out.stdout or "").strip()
        if path and os.path.isfile(path):
            return os.path.dirname(path)
    except Exception:
        pass
    default = r"C:\Program Files\Cascadeur"
    if os.path.isfile(os.path.join(default, "cascadeur.exe")):
        return default
    print("ERROR: Cascadeur not found. Start it or pass --cascadeur-dir.")
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cascadeur-dir", default=None)
    ap.add_argument("--uninstall", action="store_true")
    args = ap.parse_args()

    casc_dir = args.cascadeur_dir or detect_cascadeur_dir()
    commands_dir = os.path.join(casc_dir, "resources", "scripts", "python",
                                "commands")
    if not os.path.isdir(commands_dir):
        print(f"ERROR: {commands_dir} does not exist — wrong Cascadeur dir?")
        sys.exit(1)

    target = os.path.join(commands_dir, "mcp_bridge")
    if args.uninstall:
        if os.path.isdir(target):
            shutil.rmtree(target)
            print(f"Removed {target}")
        else:
            print("Nothing to remove.")
        return

    if os.path.isdir(target):
        shutil.rmtree(target)
    shutil.copytree(SRC, target,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"Installed bridge to {target}")
    print("No Cascadeur restart needed: the module is imported on first trigger.")


if __name__ == "__main__":
    main()
