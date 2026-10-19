# -*- coding: utf-8 -*-
"""
Wire protocol helpers for the HelixAE TCP bridges (stdlib only).

AE ExtendScript bridge (port 9888, served by the CEP panel's Node runtime):

    request  = <utf-8 encoded script bytes> + b"\\x00"
    response = <utf-8 encoded result bytes> + b"\\x00"

Exactly one request is sent per connection. Responses may arrive in multiple
chunks; a connection that closes before the response terminator is a transport
failure, never a valid empty response.

Panel command bridge (port 43210, served by HelixAE_MenuTools.py):

    request  = <command bytes> + b"\\n"
    reply    = b"ok\\n" or b"error: <reason>\\n"

The reply acknowledges that the command was accepted for dispatch to the Qt
main thread, not that the requested action has completed.

This module must stay importable without Prism or Qt (it is imported by
HelixAE_MenuTools.py before Prism is on sys.path, and by the regression
tests outside of the DCC environment).
"""

import socket
import time

AE_HOST = "127.0.0.1"
AE_PORT = 9888
AE_TERMINATOR = b"\x00"
MAX_AE_FRAME = 8 * 1024 * 1024

CMD_HOST = "127.0.0.1"
CMD_PORT = 43210
CMD_TERMINATOR = b"\n"
MAX_CMD_FRAME = 4096

KNOWN_COMMANDS = frozenset({
    "saveVersion",
    "saveExtended",
    "projectBrowser",
    "footageTracker",
    "importMedia",
    "checkIssues",
    "settings",
    "render",
    "launch",
})


class BridgeError(Exception):
    """Raised when a bridge peer violates the wire protocol."""


def _read_until(sock, terminator, max_size, what):
    chunks = []
    total = 0
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            raise BridgeError("%s: connection closed before terminator" % what)
        total += len(chunk)
        if total > max_size:
            raise BridgeError("%s: frame exceeds %d bytes" % (what, max_size))
        idx = chunk.find(terminator)
        if idx != -1:
            chunks.append(chunk[:idx])
            return b"".join(chunks)
        chunks.append(chunk)


def frame_ae_request(script):
    """Encode one ExtendScript request frame (script + null terminator)."""
    if isinstance(script, str):
        script = script.encode("utf-8")
    if AE_TERMINATOR in script:
        raise ValueError("AE request must not contain null bytes")
    return script + AE_TERMINATOR


def recv_ae_response(sock):
    """Read one null-terminated response.

    Premature EOF raises BridgeError: an empty-but-terminated response is
    returned as b"" while a dropped connection must never look like one.
    """
    return _read_until(sock, AE_TERMINATOR, MAX_AE_FRAME, "AE response")


def frame_command(cmd):
    """Encode one panel command frame (command + newline terminator)."""
    if not isinstance(cmd, str) or not cmd:
        raise ValueError("command must be a non-empty string")
    for bad in ("\n", "\r", "\x00"):
        if bad in cmd:
            raise ValueError("command must not contain control characters")
    return cmd.encode("utf-8") + CMD_TERMINATOR


def validate_command(cmd):
    return cmd in KNOWN_COMMANDS


def recv_command(sock):
    """Read and decode one newline-terminated command frame."""
    data = _read_until(sock, CMD_TERMINATOR, MAX_CMD_FRAME, "panel command")
    cmd = data.decode("utf-8")
    if not cmd:
        raise BridgeError("panel command: empty command")
    return cmd


def ok_reply():
    return b"ok\n"


def error_reply(reason):
    reason = str(reason).replace("\n", " ").replace("\r", " ").strip()
    if not reason:
        reason = "unknown error"
    return b"error: " + reason.encode("utf-8") + b"\n"


def recv_reply(sock):
    """Read one command reply; returns (ok, reason)."""
    data = _read_until(sock, CMD_TERMINATOR, MAX_CMD_FRAME, "panel command reply")
    text = data.decode("utf-8")
    if text == "ok":
        return (True, None)
    if text.startswith("error:"):
        reason = text[len("error:"):].strip()
        return (False, reason or "unknown error")
    raise BridgeError("panel command reply: unrecognized payload %r" % text)


def _default_connect(host, port, timeout):
    return socket.create_connection((host, port), timeout=timeout)


def send_command(cmd, host=CMD_HOST, port=CMD_PORT, timeout=5.0,
                 attempts=40, delay=0.25, connect=None):
    """Forward one command to the running HelixAE UI process.

    Connection failures are retried for a bounded time so commands issued
    while the owning process is still starting up are not lost. Returns
    (ok, reason); raises BridgeError if no listener could be reached at all.
    The connect parameter allows tests to substitute a fake transport.
    """
    if not validate_command(cmd):
        raise ValueError("unknown command: %r" % (cmd,))
    if connect is None:
        connect = _default_connect
    last_error = None
    for _ in range(max(1, attempts)):
        try:
            sock = connect(host, port, timeout)
        except OSError as e:
            last_error = e
            if delay > 0:
                time.sleep(delay)
            continue
        try:
            sock.sendall(frame_command(cmd))
            return recv_reply(sock)
        finally:
            sock.close()
    raise BridgeError(
        "could not connect to the HelixAE command listener on %s:%s (%s)"
        % (host, port, last_error)
    )
