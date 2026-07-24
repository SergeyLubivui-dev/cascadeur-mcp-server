"""Launch the Tools Pro companion web panel.

    python run_panel.py            # opens http://127.0.0.1:8765 in your browser
    python run_panel.py --port N   # use a different port

Keep Cascadeur running — the panel drives it through the MCP bridge.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from cascadeur_mcp_pro import panel_server  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    panel_server.main(port=args.port, open_browser=not args.no_browser)
