# -*- coding: utf-8 -*-
"""Regression tests for the HelixAE bridge wire protocol (Phase 2).

Covers the AE bridge framing (null-terminated requests/responses, premature
EOF rejection, chunked reassembly, UTF-8 split across chunks) and the panel
command bridge framing (newline-terminated commands, ok/error replies,
bounded retries, oversized frame rejection).

The module under test is loaded directly from its file path so no Prism or
Qt dependencies are required.
"""

import importlib.util
import os
import socket
import threading
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_PATH = os.path.join(REPO_ROOT, "Scripts", "helixae_bridge.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("helixae_bridge", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


br = _load_module()


class _FakeConnect(object):
    """Callable standing in for socket.create_connection in send_command."""

    def __init__(self, sockets, failures=0):
        self.sockets = sockets
        self.failures = failures
        self.attempts = 0
        self.closed = []

    def __call__(self, host, port, timeout):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise OSError("connection refused (attempt %d)" % self.attempts)
        return self.sockets.pop(0)

    def record_close(self, sock):
        self.closed.append(sock)


class AeRequestFraming(unittest.TestCase):
    def test_frames_add_single_terminator(self):
        framed = br.frame_ae_request("app.project.numItems;")
        self.assertEqual(framed, b"app.project.numItems;\x00")

    def test_accepts_bytes_input(self):
        self.assertEqual(br.frame_ae_request(b"abc"), b"abc\x00")

    def test_encodes_unicode(self):
        framed = br.frame_ae_request("Client's éclair")
        self.assertEqual(framed, "Client's éclair".encode("utf-8") + b"\x00")

    def test_rejects_embedded_null(self):
        with self.assertRaises(ValueError):
            br.frame_ae_request(b"ab\x00c")


class AeResponseReading(unittest.TestCase):
    def _pair(self):
        return socket.socketpair()

    def test_simple_response(self):
        a, b = self._pair()
        a.sendall(b"42\x00")
        a.close()
        self.assertEqual(br.recv_ae_response(b), b"42")
        b.close()

    def test_empty_but_terminated_response_is_valid(self):
        a, b = self._pair()
        a.sendall(b"\x00")
        a.close()
        self.assertEqual(br.recv_ae_response(b), b"")
        b.close()

    def test_premature_eof_raises(self):
        a, b = self._pair()
        a.sendall(b"partial without terminator")
        a.close()
        with self.assertRaises(br.BridgeError):
            br.recv_ae_response(b)
        b.close()

    def test_chunked_reassembly(self):
        a, b = self._pair()
        payload = b"x" * 300000  # > 65536, forces multiple reads
        # Send from a thread: a socketpair buffer smaller than the payload
        # would otherwise deadlock a blocking sendall before any read.
        sender = threading.Thread(
            target=lambda: (a.sendall(payload + b"\x00"), a.close())
        )
        sender.start()
        self.assertEqual(br.recv_ae_response(b), payload)
        sender.join(timeout=5)
        b.close()

    def test_terminator_split_across_chunks(self):
        a, b = self._pair()
        # Feed byte by byte so the terminator itself is split across recvs.
        for byte in b"ok":
            a.sendall(bytes([byte]))
        a.sendall(b"\x00")
        a.close()
        self.assertEqual(br.recv_ae_response(b), b"ok")
        b.close()

    def test_data_after_terminator_ignored(self):
        a, b = self._pair()
        a.sendall(b"first\x00trailing")
        a.close()
        self.assertEqual(br.recv_ae_response(b), b"first")
        b.close()

    def test_utf8_split_across_chunks(self):
        a, b = self._pair()
        text = "umaçã"
        encoded = text.encode("utf-8")
        # Split inside the multi-byte sequence.
        a.sendall(encoded[:3])
        a.sendall(encoded[3:] + b"\x00")
        a.close()
        self.assertEqual(br.recv_ae_response(b).decode("utf-8"), text)
        b.close()


class CommandFraming(unittest.TestCase):
    def test_frame_command(self):
        self.assertEqual(br.frame_command("saveVersion"), b"saveVersion\n")

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            br.frame_command("")

    def test_rejects_non_string(self):
        with self.assertRaises(ValueError):
            br.frame_command(None)
        with self.assertRaises(ValueError):
            br.frame_command(123)

    def test_rejects_control_characters(self):
        for bad in ("save\nVersion", "save\rVersion", "save\x00Version"):
            with self.assertRaises(ValueError):
                br.frame_command(bad)

    def test_validate_command(self):
        self.assertTrue(br.validate_command("saveVersion"))
        self.assertTrue(br.validate_command("launch"))
        self.assertFalse(br.validate_command("tools"))
        self.assertFalse(br.validate_command(""))
        self.assertFalse(br.validate_command("rm -rf"))


class CommandRoundTrip(unittest.TestCase):
    def _serve_once(self, response):
        server, client = socket.socketpair()

        def run():
            cmd = br.recv_command(server)
            server.sendall(response)
            server.close()

        thread = threading.Thread(target=run)
        thread.start()
        return client, thread

    def test_roundtrip_ok(self):
        client, thread = self._serve_once(br.ok_reply())
        client.sendall(br.frame_command("footageTracker"))
        ok, reason = br.recv_reply(client)
        self.assertTrue(ok)
        self.assertIsNone(reason)
        client.close()
        thread.join(timeout=5)

    def test_roundtrip_error(self):
        client, thread = self._serve_once(br.error_reply("unknown command: tools"))
        client.sendall(br.frame_command("tools"))
        ok, reason = br.recv_reply(client)
        self.assertFalse(ok)
        self.assertIn("unknown command", reason)
        client.close()
        thread.join(timeout=5)

    def test_recv_command_reads_full_frame(self):
        server, client = socket.socketpair()
        client.sendall(b"saveVer")
        client.sendall(b"sion\n")
        client.close()
        self.assertEqual(br.recv_command(server), "saveVersion")
        server.close()

    def test_recv_command_rejects_empty(self):
        server, client = socket.socketpair()
        client.sendall(b"\n")
        client.close()
        with self.assertRaises(br.BridgeError):
            br.recv_command(server)
        server.close()

    def test_recv_command_rejects_premature_eof(self):
        server, client = socket.socketpair()
        client.sendall(b"saveVer")
        client.close()
        with self.assertRaises(br.BridgeError):
            br.recv_command(server)
        server.close()

    def test_recv_command_rejects_oversized(self):
        server, client = socket.socketpair()
        client.sendall(b"a" * (br.MAX_CMD_FRAME + 1) + b"\n")
        client.close()
        with self.assertRaises(br.BridgeError):
            br.recv_command(server)
        server.close()

    def test_error_reply_sanitizes_newlines(self):
        reply = br.error_reply("line1\nline2\r\nline3")
        self.assertNotIn(b"\n", reply[:-1])
        ok, reason = self._parse(reply)
        self.assertFalse(ok)
        self.assertIn("line1", reason)

    def test_error_reply_empty_reason(self):
        ok, reason = self._parse(br.error_reply(""))
        self.assertFalse(ok)
        self.assertEqual(reason, "unknown error")

    @staticmethod
    def _parse(reply):
        a, b = socket.socketpair()
        a.sendall(reply)
        a.close()
        try:
            return br.recv_reply(b)
        finally:
            b.close()

    def test_recv_reply_rejects_unknown_payload(self):
        with self.assertRaises(br.BridgeError):
            self._parse(b"maybe\n")


class SendCommand(unittest.TestCase):
    def _autoresponder(self):
        server, client = socket.socketpair()

        def run():
            try:
                br.recv_command(server)
            except Exception:
                return
            server.sendall(br.ok_reply())
            server.close()

        thread = threading.Thread(target=run)
        thread.start()
        return client, thread

    def test_success(self):
        client, thread = self._autoresponder()
        connect = _FakeConnect([client])
        ok, reason = br.send_command(
            "render", attempts=1, delay=0, connect=connect
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)
        self.assertEqual(connect.attempts, 1)
        thread.join(timeout=5)
        # The socket must have been closed by send_command.
        self.assertTrue(client.fileno() == -1)

    def test_retries_connection_failures(self):
        client, thread = self._autoresponder()
        connect = _FakeConnect([client], failures=2)
        ok, reason = br.send_command(
            "settings", attempts=5, delay=0, connect=connect
        )
        self.assertTrue(ok)
        self.assertEqual(connect.attempts, 3)
        thread.join(timeout=5)

    def test_exhausted_retries_raise(self):
        connect = _FakeConnect([], failures=100)
        with self.assertRaises(br.BridgeError):
            br.send_command("render", attempts=3, delay=0, connect=connect)
        self.assertEqual(connect.attempts, 3)

    def test_invalid_command_rejected_before_send(self):
        with self.assertRaises(ValueError):
            br.send_command("not a command?", attempts=1, delay=0,
                            connect=_FakeConnect([]))


if __name__ == "__main__":
    unittest.main()
