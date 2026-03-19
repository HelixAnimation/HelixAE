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
import platform
import shutil
import zipfile
import time

if platform.system() == "Windows":
    import winreg as _winreg

from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher_plugin as err_catcher


class HelixAE_Integration(object):
    def __init__(self, core, plugin):
        self.core = core
        self.plugin = plugin

        if platform.system() == "Windows":
            self.examplePath = os.environ["APPDATA"].replace("\\", "/") + "/Adobe/CEP/extensions"
        elif platform.system() == "Darwin":
            self.examplePath = os.path.expanduser("~/Library/Application Support/Adobe/CEP/extensions")

        if not os.path.exists(self.examplePath):
            try:
                os.makedirs(self.examplePath)
            except Exception:
                pass

    @err_catcher(name=__name__)
    def getExecutable(self):
        execPath = ""
        if platform.system() == "Windows":
            defaultpath = os.path.join(self.getAfterEffectsPath() or "", "AfterFX.exe")
            if os.path.exists(defaultpath):
                execPath = defaultpath

        return execPath

    @err_catcher(name=__name__)
    def getAfterEffectsPath(self):
        paths = self.getAfterEffectsPaths()
        if not paths:
            return

        return paths[0]

    @err_catcher(name=__name__)
    def getAfterEffectsPaths(self):
        try:
            key = _winreg.OpenKey(
                _winreg.HKEY_LOCAL_MACHINE,
                "SOFTWARE\\Adobe\\After Effects",
                0,
                _winreg.KEY_READ | _winreg.KEY_WOW64_64KEY,
            )

            versions = []
            try:
                i = 0
                while True:
                    vers = _winreg.EnumKey(key, i)
                    try:
                        float(vers)
                    except Exception:
                        pass
                    else:
                        versions.append(vers)

                    i += 1
            except WindowsError:
                pass

            paths = []
            for version in reversed(versions):
                key = _winreg.OpenKey(
                    _winreg.HKEY_LOCAL_MACHINE,
                    "SOFTWARE\\Adobe\\After Effects\\%s" % version,
                    0,
                    _winreg.KEY_READ | _winreg.KEY_WOW64_64KEY,
                )

                try:
                    installDir = _winreg.QueryValueEx(key, "installPath")[0]
                except Exception:
                    continue

                paths.append(installDir)

            return paths
        except Exception:
            return []

    @err_catcher(name=__name__)
    def addIntegration(self, installPath):
        try:
            integrationBase = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "Integration"
            )
            integrationBase = os.path.realpath(integrationBase)

            cmds = []
            origAepZip = os.path.join(integrationBase, "helixae.zip")
            targetFolder = os.path.join(installPath, "helixae")
            if os.path.exists(targetFolder):
                cmd = {
                    "type": "removeFolder",
                    "args": [targetFolder],
                    "validate": False,
                }
                cmds.append(cmd)

            origFile = os.path.join(integrationBase, "helixae.cmd")
            targetFile = os.path.join(installPath, "helixae.cmd")
            if os.path.exists(targetFile):
                cmd = {
                    "type": "removeFile",
                    "args": [targetFile],
                    "validate": False,
                }
                cmds.append(cmd)

            cmd = {"type": "copyFile", "args": [origFile, targetFile]}
            cmds.append(cmd)

            with open(origFile, "r") as init:
                initStr = init.read()

            initStr = initStr.replace("PLUGINROOT", "%s" % self.pluginDirectory.replace("\\", "/"))
            initStr = initStr.replace("PRISMROOT", "%s" % self.core.prismRoot)
            cmd = {"type": "writeToFile", "args": [targetFile, initStr]}
            cmds.append(cmd)

            result = self.core.runFileCommands(cmds)
            if result:
                result = self.extractZipWithDates(origAepZip, targetFolder)

            if result is True:
                return True
            elif result is False:
                return False
            else:
                raise Exception(result)

        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()

            msgStr = (
                "Errors occurred during the installation of the HelixAE integration.\n"
                "The installation is possibly incomplete.\n\n%s\n%s\n%s"
                % (str(e), exc_type, exc_tb.tb_lineno)
            )
            msgStr += "\n\nRunning this application as administrator could solve this problem eventually."
            self.core.popup(msgStr)
            return False

    @err_catcher(name=__name__)
    def extractZipWithDates(self, zipPath, extractTo):
        try:
            with zipfile.ZipFile(zipPath, "r") as zipRef:
                for zipInfo in zipRef.infolist():
                    extractedPath = os.path.join(extractTo, zipInfo.filename)
                    if zipInfo.is_dir():
                        os.makedirs(extractedPath, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(extractedPath), exist_ok=True)
                        zipRef.extract(zipInfo, extractTo)

                    modTime = zipInfo.date_time
                    timestamp = time.mktime(modTime + (0, 0, -1))
                    os.utime(extractedPath, (timestamp, timestamp))
        except Exception as e:
            return str(e)
        else:
            return True

    def removeIntegration(self, installPath):
        try:
            heAep = os.path.join(installPath, "helixae")
            heCmd = os.path.join(installPath, "helixae.cmd")
            if os.path.exists(heAep):
                shutil.rmtree(heAep)

            if os.path.exists(heCmd):
                os.remove(heCmd)

            return True

        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            msgStr = (
                "Errors occurred during the removal of the HelixAE integration.\n\n%s\n%s\n%s"
                % (str(e), exc_type, exc_tb.tb_lineno)
            )
            msgStr += "\n\nRunning this application as administrator could solve this problem eventually."
            self.core.popup(msgStr)
            return False

    def updateInstallerUI(self, userFolders, pItem):
        try:
            pluginItem = QTreeWidgetItem([self.plugin.pluginName])
            pItem.addChild(pluginItem)

            pluginPath = self.examplePath

            if pluginPath is not None and os.path.exists(pluginPath):
                pluginItem.setCheckState(0, Qt.Checked)
                pluginItem.setText(1, pluginPath)
                pluginItem.setToolTip(0, pluginPath)
            else:
                pluginItem.setCheckState(0, Qt.Unchecked)
                pluginItem.setText(1, "< doubleclick to browse path >")
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            msg = (
                "Errors occurred during the installation.\n The installation is possibly incomplete.\n\n"
                "%s\n%s\n%s\n%s" % (__file__, str(e), exc_type, exc_tb.tb_lineno)
            )
            self.core.popup(msg)
            return False

    def installerExecute(self, pluginItem, result):
        try:
            pluginPaths = []
            installLocs = []

            if pluginItem.checkState(0) != Qt.Checked:
                return installLocs

            if pluginItem.checkState(0) == Qt.Checked and os.path.exists(pluginItem.text(1)):
                pluginPaths.append(pluginItem.text(1))

            for pluginPath in pluginPaths:
                result[
                    "HelixAE integration"
                ] = self.core.integration.addIntegration(
                    self.plugin.pluginName, path=pluginPath, quiet=True
                )
                if result["HelixAE integration"]:
                    installLocs.append(pluginPath)

            return installLocs
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            msg = (
                "Errors occurred during the installation.\n The installation is possibly incomplete.\n\n"
                "%s\n%s\n%s\n%s" % (__file__, str(e), exc_type, exc_tb.tb_lineno)
            )
            self.core.popup(msg)
            return False
