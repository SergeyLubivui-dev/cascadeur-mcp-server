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

_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(_ROOT, "cascadeur_side", "mcp_bridge")
# extra command packages installed alongside the bridge (name -> source dir)
EXTRA_PACKAGES = {
    "tools_pro": os.path.join(_ROOT, "cascadeur_side", "tools_pro"),
}


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
    packages = [("mcp_bridge", SRC, target)]
    for name, src in EXTRA_PACKAGES.items():
        if os.path.isdir(src):
            packages.append((name, src, os.path.join(commands_dir, name)))

    if args.uninstall:
        for name, _src, dst in packages:
            if os.path.isdir(dst):
                shutil.rmtree(dst)
                print(f"Removed {dst}")
        return

    for name, src, dst in packages:
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        print(f"Installed {name} to {dst}")
    print("The bridge is imported on first trigger. Tools Pro commands appear in "
          "Cascadeur's command list after a command reload / restart.")


if __name__ == "__main__":
    main()
