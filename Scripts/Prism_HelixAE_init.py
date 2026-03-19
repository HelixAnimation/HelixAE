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


from HelixAE_Variables import HelixAE_Variables
from HelixAE_externalAccess_Functions import HelixAE_externalAccess_Functions
from HelixAE_Functions import HelixAE_Functions
from HelixAE_Integration import HelixAE_Integration
from helixae_core import HelixAECore
from helixae_export import HelixAE_Export


class Prism_HelixAE(
    HelixAE_Variables,
    HelixAE_externalAccess_Functions,
    HelixAE_Functions,
    HelixAE_Integration,
):
    def __init__(self, core):
        HelixAE_Variables.__init__(self, core, self)
        HelixAE_externalAccess_Functions.__init__(self, core, self)
        HelixAE_Functions.__init__(self, core, self)
        HelixAE_Integration.__init__(self, core, self)


# Alias for backward compatibility
Prism_Plugin_HelixAE = Prism_HelixAE
HelixAE_Plugin = Prism_HelixAE
