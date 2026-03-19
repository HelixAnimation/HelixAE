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


class HelixAE_Variables(object):
    def __init__(self, core, plugin):
        self.version = "v1.0.0"
        self.pluginName = "HelixAE"
        self.pluginType = "App"
        self.appShortName = "HelixAE"
        self.appType = "2d"
        self.hasQtParent = False
        self.sceneFormats = [".aep"]
        self.appSpecificFormats = self.sceneFormats
        self.outputFormats = []
        self.appColor = [25, 71, 154]
        self.platforms = ["Windows", "Darwin"]
        self.pluginDirectory = os.path.abspath(
            os.path.dirname(os.path.dirname(__file__))
        )
        self.appIcon = os.path.join(self.pluginDirectory, "Resources", "HelixAE.ico")
