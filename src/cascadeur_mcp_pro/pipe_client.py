"""Direct IPC channel to a running Cascadeur via its single-instance QLocalServer
named pipe — an alternative to spawning `cascadeur.exe --run-script` per call
(~1.5-2s each). The pipe is Cascadeur's OWN command channel (the mechanism that
forwards --run-script to the master instance); this is not a license bypass.

STATUS: discovery + connectivity WORK. The exact Qt QDataStream framing of the
`run-python-code` request still needs ONE wire capture (Process Monitor / API
Monitor on a live --run-script) to finalize send(). Until then the MCP uses the
--run-script bridge; this module lets us discover/verify the pipe and is the
drop-in fast path once the framing is confirmed.

Found command verbs in cascadeur.exe: run-script, run-python-code,
single-user-mode, logger-silent-mode. Pipe name pattern:
  \\.\pipe\Cascadeur.instancesManager.<hex>.server
"""

from __future__ import annotations

import glob
import os
import struct

PIPE_GLOB = r"\\.\pipe\Cascadeur.instancesManager.*.server"


def find_pipe() -> str | None:
    """Return the Cascadeur instance-manager pipe path, or None if not running."""
    matches = glob.glob(PIPE_GLOB)
    return matches[0] if matches else None


def can_connect() -> dict:
    """Test whether the pipe exists and can be opened for read/write."""
    pipe = find_pipe()
    if not pipe:
        return {"pipe": None, "connectable": False}
    try:
        fd = os.open(pipe, os.O_RDWR | os.O_BINARY)
        os.close(fd)
        return {"pipe": pipe, "connectable": True}
    except OSError as e:
        return {"pipe": pipe, "connectable": False, "error": str(e)}


def _qstring_block(s: str) -> bytes:
    """Qt QDataStream QString: quint32 byte length (BE) + UTF-16BE. A leading
    quint32 total-size block prefix is common for QLocalSocket messages."""
    body = s.encode("utf-16-be")
    return struct.pack(">I", len(body)) + body


def send_run_python(code: str, verb: str = "run-python-code") -> dict:
    """EXPERIMENTAL: send a run-python-code request over the pipe. The framing
    below is the most likely Qt pattern (block-size prefix + verb + payload);
    confirm against one captured message before trusting it. Falls back cleanly
    (returns not_confirmed) rather than sending guessed bytes that could
    destabilize Cascadeur."""
    pipe = find_pipe()
    if not pipe:
        return {"ok": False, "error": "pipe not found (Cascadeur not running)"}
    # Do NOT send unconfirmed bytes by default — that risks crashing the app.
    return {"ok": False, "not_confirmed": True, "pipe": pipe,
            "note": "framing for %r needs one wire capture; use the --run-script "
                    "bridge until confirmed" % verb,
            "candidate_message_preview": len(_qstring_block(verb) + _qstring_block(code))}
