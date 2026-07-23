"""TCP bridge client: triggers the in-Cascadeur bridge and exchanges op batches.

Flow per session:
1. We listen on 127.0.0.1:<port> and write the port to %TEMP%/cascadeur_mcp_pro.json.
2. We spawn ``cascadeur.exe --run-script commands.mcp_bridge.exec_bridge``.
   With a GUI instance already running, the new process forwards the argument to it
   and exits; the script then runs on Cascadeur's main thread.
3. The bridge connects back, sends a hello, and serves batches until we send "end".
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import threading
import time
from typing import Any

_HEADER = 12
BRIDGE_MODULE = "commands.mcp_bridge.exec_bridge"
PORT_FILE = os.path.join(tempfile.gettempdir(), "cascadeur_mcp_pro.json")

DEFAULT_PORT = int(os.environ.get("CASCADEUR_MCP_PORT", "53621"))
CONNECT_TIMEOUT = float(os.environ.get("CASCADEUR_MCP_TIMEOUT", "15"))
CONNECT_ATTEMPTS = int(os.environ.get("CASCADEUR_MCP_ATTEMPTS", "3"))


class BridgeError(RuntimeError):
    pass


def _detect_cascadeur_exe() -> str:
    env = os.environ.get("CASCADEUR_EXE_PATH")
    if env and os.path.isfile(env):
        return env
    # A running instance is the best source of truth.
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Process cascadeur -ErrorAction SilentlyContinue | "
             "Select-Object -First 1).Path"],
            capture_output=True, text=True, timeout=15)
        path = (out.stdout or "").strip()
        if path and os.path.isfile(path):
            return path
    except Exception:
        pass
    for candidate in (r"C:\Program Files\Cascadeur\cascadeur.exe",):
        if os.path.isfile(candidate):
            return candidate
    raise BridgeError(
        "cascadeur.exe not found. Start Cascadeur or set CASCADEUR_EXE_PATH.")


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("bridge socket closed")
        buf += chunk
    return buf


def _recv_json(sock: socket.socket) -> dict:
    length = int(_recv_exact(sock, _HEADER).decode("ascii").strip())
    return json.loads(_recv_exact(sock, length).decode("utf-8"))


def _send_json(sock: socket.socket, obj: dict) -> None:
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sock.sendall(str(len(data)).ljust(_HEADER).encode("ascii") + data)


class BridgeSession:
    """One connected bridge session (Cascadeur main thread is inside our loop)."""

    def __init__(self, conn: socket.socket, hello: dict):
        self._conn = conn
        self.hello = hello

    def call(self, requests: list[dict]) -> list[dict]:
        _send_json(self._conn, {"requests": requests})
        reply = _recv_json(self._conn)
        return reply.get("responses", [])

    def reload_ops(self) -> dict:
        _send_json(self._conn, {"reload": True})
        return _recv_json(self._conn)

    def close(self) -> None:
        try:
            _send_json(self._conn, {"end": True})
        except Exception:
            pass
        try:
            self._conn.close()
        except Exception:
            pass


class BridgeClient:
    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self._lock = threading.Lock()
        self._listener: socket.socket | None = None
        self._exe: str | None = None
        self._persistent: BridgeSession | None = None
        self.last_latency: float | None = None

    # -------------------------------------------------- infrastructure

    def _ensure_listener(self) -> socket.socket:
        if self._listener is not None:
            return self._listener
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", self.port))
        srv.listen(4)
        self._listener = srv
        with open(PORT_FILE, "w", encoding="utf-8") as f:
            json.dump({"port": self.port}, f)
        return srv

    def cascadeur_exe(self) -> str:
        if self._exe is None:
            self._exe = _detect_cascadeur_exe()
        return self._exe

    def _trigger(self) -> None:
        subprocess.Popen(
            [self.cascadeur_exe(), "--run-script", BRIDGE_MODULE],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def is_running(self) -> bool:
        """Fast check whether a Cascadeur GUI process is alive."""
        try:
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq cascadeur.exe", "/NH"],
                capture_output=True, text=True, timeout=10)
            return "cascadeur.exe" in (out.stdout or "").lower()
        except Exception:
            return True  # assume running; the trigger will tell us

    def ensure_running(self, wait: float = 40.0) -> bool:
        """Crash-recovery: if Cascadeur is down, relaunch the GUI and wait for it
        to come up (so the next trigger lands on a warm instance)."""
        if self.is_running():
            return True
        subprocess.Popen([self.cascadeur_exe()],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            time.sleep(3)
            if self.is_running():
                time.sleep(6)  # let the script host initialise
                return True
        return False

    def open_session(self) -> BridgeSession:
        srv = self._ensure_listener()
        # Drain any stale queued connections before triggering a fresh one.
        srv.settimeout(0.01)
        try:
            while True:
                stale, _ = srv.accept()
                stale.close()
        except (socket.timeout, OSError):
            pass

        started = time.monotonic()
        conn = None
        # A --run-script trigger is occasionally dropped by the running
        # instance; retry a couple of times, and relaunch on a crash.
        for attempt in range(CONNECT_ATTEMPTS):
            if attempt == CONNECT_ATTEMPTS - 1:
                # last chance: make sure the app is actually up (crash recovery)
                self.ensure_running()
            self._trigger()
            srv.settimeout(CONNECT_TIMEOUT)
            try:
                conn, _ = srv.accept()
                break
            except socket.timeout:
                continue
        if conn is None:
            raise BridgeError(
                "Cascadeur bridge did not connect (%d attempts x %.0fs). Is "
                "Cascadeur running and is the bridge installed "
                "(run install_bridge.py)?" % (CONNECT_ATTEMPTS, CONNECT_TIMEOUT))
        conn.settimeout(max(CONNECT_TIMEOUT, 60.0))
        hello = _recv_json(conn)
        self.last_latency = time.monotonic() - started
        return BridgeSession(conn, hello)

    # -------------------------------------------------- persistent session

    def session(self):
        """Context manager: hold ONE bridge session open for many run_ops calls,
        so a whole build pays the ~2s --run-script trigger ONCE instead of per
        call. NOTE: while the session is open the bridge blocks Cascadeur's main
        thread whenever it waits for the next batch, so the UI is frozen for the
        session's duration — scope this tightly around a headless build.

            with client.session():
                client.run_ops([...])   # fast — reuses the open session
                client.run_op(...)
        """
        client = self

        class _Ctx:
            def __enter__(self_):
                with client._lock:
                    if client._persistent is None:
                        client._persistent = client.open_session()
                return client

            def __exit__(self_, *exc):
                with client._lock:
                    if client._persistent is not None:
                        try:
                            client._persistent.close()
                        finally:
                            client._persistent = None
                return False

        return _Ctx()

    # -------------------------------------------------- public API

    def run_ops(self, requests: list[dict], reload_ops: bool = False) -> list[dict]:
        """Run a batch of ops. Reuses the persistent session if one is open
        (see .session()), else opens+closes a one-shot session. Thread-safe."""
        for i, r in enumerate(requests):
            r.setdefault("id", i)
        with self._lock:
            if self._persistent is not None:
                if reload_ops:
                    try:
                        self._persistent.reload_ops()
                    except (ConnectionError, socket.timeout, OSError):
                        self._persistent = self.open_session()
                try:
                    return self._persistent.call(requests)
                except (ConnectionError, socket.timeout, OSError):
                    # session died (idle timeout / crash) — reopen once and retry
                    self._persistent = self.open_session()
                    return self._persistent.call(requests)
            session = self.open_session()
            try:
                if reload_ops:
                    session.reload_ops()
                return session.call(requests)
            finally:
                session.close()

    def run_op(self, op: str, args: dict | None = None,
               reload_ops: bool = False) -> Any:
        """Run one op and return its result; raise BridgeError on op failure."""
        responses = self.run_ops([{"op": op, "args": args or {}}],
                                 reload_ops=reload_ops)
        if not responses:
            raise BridgeError("empty response from bridge")
        resp = responses[0]
        if resp.get("status") != "ok":
            err = resp.get("error", "unknown bridge error")
            stdout = resp.get("stdout")
            if stdout:
                err += "\n--- stdout ---\n" + stdout
            raise BridgeError(err)
        return resp.get("result"), resp.get("stdout")
