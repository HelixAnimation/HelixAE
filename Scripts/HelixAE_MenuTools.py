# -*- coding: utf-8 -*-
#
####################################################
#
# Helix AE - Pipeline extension for Adobe After Effects
#
# Copyright (C) 2016-2025 Richard Frangenberg
# Copyright (C) 2023 Prism Software GmbH
# Copyright (C) 2025 Helix Project Contributors
#
# Licensed under GNU LGPL-3.0-or-later
#
# This file is part of Helix AE (based on Prism).
#
# Helix AE is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Helix AE is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with Helix AE.  If not, see <https://www.gnu.org/licenses/>.


import os
import sys
import json
import socket
import threading
import platform
import ctypes
from ctypes import wintypes

# Prism's embedded Python runs in isolated mode (python313._pth: no site, and
# this script's directory is not added to sys.path), so the plugin's own
# Scripts folder must be inserted before sibling modules are importable.
_PLUGIN_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_SCRIPTS not in sys.path:
    sys.path.insert(0, _PLUGIN_SCRIPTS)

try:
    import helixae_bridge
except ImportError as _e:
    # No Qt is available yet; fail loudly instead of exiting with a bare code.
    _msg = (
        "HelixAE failed to import helixae_bridge.py from:\n%s\n\n(%s)\n"
        "Check that the NAS deployment of the plugin is complete."
        % (_PLUGIN_SCRIPTS, _e)
    )
    print("[HelixAE] " + _msg)
    if platform.system() == "Windows":
        ctypes.windll.user32.MessageBoxW(None, _msg, "HelixAE", 0x10)
    raise

CMD_HOST = helixae_bridge.CMD_HOST
CMD_PORT = helixae_bridge.CMD_PORT

# Resolve the startup command before any singleton decision so both the
# primary and the forwarding path use the same default.
initial_cmd = sys.argv[1] if len(sys.argv) > 1 else "projectBrowser"

if not helixae_bridge.validate_command(initial_cmd):
    print("[HelixAE] Unknown command: %s" % initial_cmd)
    sys.exit(1)

mutex = None
if platform.system() == "Windows":
    # Check if another instance is running using a named mutex
    mutex_name = "Global\\HelixAEMutex"
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.GetLastError.restype = wintypes.DWORD
    mutex = kernel32.CreateMutexW(None, True, mutex_name)
    last_error = kernel32.GetLastError()

    if not mutex:
        # Cannot prove ownership either way; keep running but make it visible.
        print("[HelixAE] Warning: could not create the singleton mutex; continuing.")
    elif last_error == 183:  # ERROR_ALREADY_EXISTS
        # Another instance is running: forward the command to it and exit.
        # Connection retries cover the window while the owner is still starting.
        try:
            ok, reason = helixae_bridge.send_command(
                initial_cmd, host=CMD_HOST, port=CMD_PORT
            )
        except helixae_bridge.BridgeError as e:
            ok, reason = False, str(e)
        if not ok:
            print(
                "[HelixAE] Running HelixAE instance did not accept '%s': %s"
                % (initial_cmd, reason)
            )
            sys.exit(1)
        sys.exit(0)

prismRoot = os.environ.get("PRISM_ROOT")
if not prismRoot:
    raise Exception("PRISM_ROOT environment variable not set!")

sys.path.insert(0, os.path.join(prismRoot, "Scripts"))
import PrismCore

from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *


class CommandHandler(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending = []
        self._pending_lock = threading.Lock()

    @Slot(str)
    def handleCmd(self, cmd):
        # Always executed on the Qt main thread via queued connections. Prism
        # may still be initializing (splash / nested event loops), in which
        # case the command is queued until PrismCore.create() has finished.
        if globals().get("pcore") is None:
            with self._pending_lock:
                self._pending.append(cmd)
            print("[HelixAE] Prism is still loading; queued command: %s" % cmd)
            return
        self.executeCmd(cmd)

    def flushPending(self):
        with self._pending_lock:
            pending = self._pending
            self._pending = []
        for cmd in pending:
            self.executeCmd(cmd)

    def executeCmd(self, cmd):
        if cmd == "saveVersion":
            pcore.saveScene()
            self._patchVersionInfo(pcore)
        elif cmd == "saveExtended":
            result = pcore.saveWithComment()
            if result:
                self._patchVersionInfo(pcore)
        elif cmd == "projectBrowser":
            pcore.projectBrowser()
        elif cmd == "importMedia":
            pcore.appPlugin.openImportDialog()
        elif cmd == "checkIssues":
            pcore.appPlugin.checkIssues()
        elif cmd == "settings":
            pcore.prismSettings()
        elif cmd == "render":
            pcore.appPlugin.openRenderDlg()
        elif cmd == "footageTracker":
            pcore.appPlugin.openFootageTracker()
        elif cmd == "launch":
            # Only used by the panel's initial auto-launch: opening Prism
            # itself is the whole action, nothing further to dispatch.
            pass
        else:
            print("[HelixAE] Ignoring unknown command: %s" % cmd)

    def _patchVersionInfo(self, pcore):
        """Patch versioninfo.json with dependencies from the save.

        Delegates to the plugin's own ae_core implementation
        (HelixAECore._patchVersionInfo) so there is exactly one patch
        path; it prefers the archive data owned by the save that just
        happened and falls back to reading _archiveinfo.json from disk.
        """
        try:
            app_plugin = getattr(pcore, "appPlugin", None)
            ae_core = getattr(app_plugin, "ae_core", None)
            if ae_core is None:
                print("[HelixAE] ae_core not available; skipping versioninfo patch")
                return
            current_file = pcore.getCurrentFileName()
            if not current_file or not current_file.endswith('.aep'):
                return
            ae_core._patchVersionInfo(current_file)
        except Exception as e:
            print(f"[HelixAE] Failed to patch versioninfo: {e}")


commandHandler = CommandHandler()

qapp = QApplication.instance()
if qapp is None:
    qapp = QApplication(sys.argv)

QApplication.instance().setQuitOnLastWindowClosed(False)


def handle_client_connection(client_socket):
    with client_socket:
        try:
            cmd = helixae_bridge.recv_command(client_socket)
        except helixae_bridge.BridgeError as e:
            print("[HelixAE] Invalid command frame: %s" % e)
            return
        if not helixae_bridge.validate_command(cmd):
            print("[HelixAE] Rejecting unknown command: %s" % cmd)
            client_socket.sendall(
                helixae_bridge.error_reply("unknown command: %s" % cmd)
            )
            return
        invoked = QMetaObject.invokeMethod(
            commandHandler, "handleCmd", Qt.QueuedConnection, Q_ARG(str, cmd)
        )
        if invoked:
            client_socket.sendall(helixae_bridge.ok_reply())
        else:
            client_socket.sendall(
                helixae_bridge.error_reply("could not queue command for dispatch")
            )


def serve_commands(server_socket):
    while True:
        client_socket, _ = server_socket.accept()
        threading.Thread(
            target=handle_client_connection, args=(client_socket,), daemon=True
        ).start()


# Bind synchronously in the main thread so a port conflict is a visible
# startup failure instead of a silently dead command listener.
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    server_socket.bind((CMD_HOST, CMD_PORT))
    server_socket.listen()
except OSError as e:
    raise Exception(
        "HelixAE command listener cannot bind %s:%s (%s). "
        "Another HelixAE process may be running without the singleton mutex."
        % (CMD_HOST, CMD_PORT, e)
    )
threading.Thread(target=serve_commands, args=(server_socket,), daemon=True).start()

if initial_cmd == "launch":
    prismArgs = ["loadProject", "splash"]
else:
    prismArgs = ["loadProject", "noProjectBrowser", "splash"]

pcore = PrismCore.create(app="HelixAE", prismArgs=prismArgs)

# Prism is ready: run commands that were forwarded while it was loading,
# then dispatch this process' own startup command.
commandHandler.flushPending()
QMetaObject.invokeMethod(
    commandHandler, "handleCmd", Qt.QueuedConnection, Q_ARG(str, initial_cmd)
)

sys.exit(qapp.exec_())
