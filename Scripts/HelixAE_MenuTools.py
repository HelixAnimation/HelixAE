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

socket_address = ('localhost', 65432)


def handle_client_connection(client_socket):
    with client_socket:
        data = client_socket.recv(1024)
        if data:
            cmd = data.decode()
            QMetaObject.invokeMethod(commandHandler, "handleCmd", Qt.QueuedConnection, Q_ARG(str, cmd))


def start_socket_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind(socket_address)
        server_socket.listen()
        while True:
            client_socket, _ = server_socket.accept()
            threading.Thread(target=handle_client_connection, args=(client_socket,)).start()


if platform.system() == "Windows":
    # Check if another instance is running using a named mutex
    mutex_name = "Global\\HelixAEMutex"
    mutex = ctypes.windll.kernel32.CreateMutexW(None, wintypes.BOOL(True), mutex_name)
    last_error = ctypes.windll.kernel32.GetLastError()

    if last_error == 183:  # ERROR_ALREADY_EXISTS
        # Another instance is running, send a command to it
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect(socket_address)
            client_socket.sendall(sys.argv[1].encode())
        sys.exit(0)

threading.Thread(target=start_socket_server, daemon=True).start()

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

    @Slot(str)
    def handleCmd(self, cmd):
        if "pcore" not in globals():
            print("Prism is still loading. Please wait a moment and try again.")
            return

        if cmd == "tools":
            result = pcore.appPlugin.openAfterEffectsTools()
        elif cmd == "saveVersion":
            pcore.saveScene()
            self._patchVersionInfo(pcore)
            result = None
        elif cmd == "saveExtended":
            result = pcore.saveWithComment()
            if result:
                self._patchVersionInfo(pcore)
        elif cmd == "projectBrowser":
            result = pcore.projectBrowser()
        elif cmd == "importMedia":
            result = pcore.appPlugin.openImportDialog()
        elif cmd == "checkIssues":
            result = pcore.appPlugin.checkIssues()
        elif cmd == "settings":
            result = pcore.prismSettings()
        elif cmd == "render":
            result = pcore.appPlugin.openRenderDlg()
        elif cmd == "launch":
            result = True
        elif cmd == "footageTracker":
            result = pcore.appPlugin.openFootageTracker()
        else:
            pcore.popup(cmd)

        return result


    def _patchVersionInfo(self, pcore):
        """Patch versioninfo.json with dependencies and externalFiles from archiveinfo.json."""
        try:
            current_file = pcore.getCurrentFileName()
            if not current_file or not current_file.endswith('.aep'):
                return

            base = os.path.splitext(current_file)[0]
            versioninfo_path = base + "versioninfo.json"
            archiveinfo_path = base + "_archiveinfo.json"

            if not os.path.exists(versioninfo_path) or not os.path.exists(archiveinfo_path):
                return

            with open(archiveinfo_path, 'r') as f:
                archive = json.load(f)
            with open(versioninfo_path, 'r') as f:
                vinfo = json.load(f)

            source_paths = archive.get("source_paths", {})
            dependencies = [
                p.replace("\\", "/") for p in
                source_paths.get("3d_renders", []) +
                source_paths.get("2d_renders", [])
            ]
            external_files = [
                p.replace("\\", "/") for p in
                source_paths.get("resources", []) +
                archive.get("external_paths", [])
            ]

            if dependencies:
                vinfo["dependencies"] = dependencies
            if external_files:
                vinfo["externalFiles"] = external_files

            with open(versioninfo_path, 'w') as f:
                json.dump(vinfo, f, indent=2)

        except Exception as e:
            print(f"[HelixAE] Failed to patch versioninfo.json: {e}")


commandHandler = CommandHandler()

qapp = QApplication.instance()
if qapp is None:
    qapp = QApplication(sys.argv)

QApplication.instance().setQuitOnLastWindowClosed(False)

if len(sys.argv) > 1 and sys.argv[1] == "launch":
    prismArgs = ["loadProject", "splash"]
else:
    prismArgs = ["loadProject", "noProjectBrowser", "splash"]

pcore = PrismCore.create(app="HelixAE", prismArgs=prismArgs)
cmd = sys.argv[1] if len(sys.argv) > 1 else "projectBrowser"
result = QMetaObject.invokeMethod(commandHandler, "handleCmd", Qt.QueuedConnection, Q_ARG(str, cmd))
if result:
    qapp.exec_()
