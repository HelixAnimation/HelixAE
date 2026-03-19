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


def load_stylesheet():
    sFile = os.path.dirname(__file__) + "/HelixAE.qss"
    if not os.path.exists(sFile):
        return ""

    with open(sFile, "r") as f:
        stylesheet = f.read()

    ssheetDir = os.path.dirname(sFile)
    ssheetDir = ssheetDir.replace("\\", "/") + "/"

    repl = {
        "qss:": ssheetDir,
        "@mainBackground1": "rgb(35, 35, 35)",
        "@borders": "rgb(90, 90, 90)",
        "@tableHeader": "rgb(28, 28, 28)",
        "@selectionBackgroundColor": "rgb(25, 71, 154)",
        "@selectionBackgroundHoverColor": "rgb(168, 168, 168)",
        "@selectionHoverColor": "rgb(43, 43, 43)",
        "@selectionColor": "rgb(255, 255, 255)",
        "@menuBackground": "rgb(29, 29, 29)",
        "@menuhoverbackground": "rgb(69, 69, 69)",
        "@menuSelectionbackground": "rgb(77, 77, 77)",
        "@buttonBackgroundDefault": "rgb(61, 61, 61)",
        "@buttonBackgroundDisabled": "rgb(55, 55, 55)",
        "@buttonBackgroundHover": "rgb(77, 77, 77)",
        "@buttonBackgroundBright1": "rgb(67, 67, 67)",
        "@buttonBackgroundBright2": "rgb(26, 26, 26)",
        "@white": "rgb(192, 192, 192)",
        "@tableBackground": "rgb(28, 28, 28)",
        "@inputHover": "rgb(31, 31, 31)",
        "@inputBackground": "rgb(28, 28, 28)",
        "@inputFocus": "rgb(28, 28, 28)",
        "@test": "rgb(200, 49, 49)",
        "@lightgrey": "rgb(190, 190, 190)",
        "@disabledText": "rgb(105, 105, 105)",
        "@tableBorders": "rgb(90, 90, 90)",
        "@scrollHandleColor": "rgb(49, 49, 49)",
        "@scrollHandleHoverColor": "rgb(69, 69, 69)",
    }

    for key in repl:
        stylesheet = stylesheet.replace(key, repl[key])

    return stylesheet
