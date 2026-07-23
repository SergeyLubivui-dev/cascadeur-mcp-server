"""Quick end-to-end bridge test without the MCP layer.

Usage: python test_bridge.py <op> [json-args]
       python test_bridge.py --batch '<json list of {"op","args"}>'
"""

import json
import sys
import time

sys.path.insert(0, "src")
from cascadeur_mcp_pro.bridge_client import BridgeClient


def main():
    client = BridgeClient()
    if len(sys.argv) > 2 and sys.argv[1] == "--batch-file":
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            requests = json.load(f)
        t0 = time.monotonic()
        responses = client.run_ops(requests)
        dt = time.monotonic() - t0
        print(json.dumps(responses, indent=2, ensure_ascii=False))
    elif len(sys.argv) > 2 and sys.argv[1] == "--batch":
        requests = json.loads(sys.argv[2])
        t0 = time.monotonic()
        responses = client.run_ops(requests)
        dt = time.monotonic() - t0
        print(json.dumps(responses, indent=2, ensure_ascii=False))
    else:
        op = sys.argv[1] if len(sys.argv) > 1 else "scene.info"
        args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        t0 = time.monotonic()
        try:
            result, stdout = client.run_op(op, args)
        except Exception as e:
            print("ERROR:", e)
            sys.exit(1)
        dt = time.monotonic() - t0
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if stdout:
            print("--- stdout ---")
            print(stdout)
    print(f"[latency: trigger->hello {client.last_latency:.2f}s, total {dt:.2f}s]",
          file=sys.stderr)


if __name__ == "__main__":
    main()
