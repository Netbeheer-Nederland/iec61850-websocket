# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025 Netbeheer Nederland
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
CDC (Common Data Class) registry.

Maps lowercase CDC name strings (as they appear on the wire and in JSON model
definitions) to factory functions that construct the complete DataObject tree
for that CDC, including all required DataAttributes.

Usage::

    factory = CdcRegistry.get_factory("mv")
    do = factory("TotW", parent_ln)
"""

from typing import Callable

from ws61850.iec61850.data_model import helper
from ws61850.iec61850.data_model.ied_model import DataObject

CdcFactory = Callable[[str, object], DataObject]

_REGISTRY: dict[str, CdcFactory] = {
    "mv": helper.create_mv_do,
    "asg": helper.create_asg_do,
    "asg_custom": helper.create_asg_do_custom,
    "apc": helper.create_apc_do,
    "inc": helper.create_inc_do,
    "ens": helper.create_ens_do,
    "sps": helper.create_sps_do,
    "enc": helper.create_enc_do,
    "lpl": helper.create_lpl_do,
    "dpl": helper.create_dpl_do,
    "cmv": helper.create_cmv_do,
    "ing": helper.create_ing_do,
    "wye": helper.create_wye_do,
    "del": helper.create_del_do,
}


class CdcRegistry:
    @staticmethod
    def get_factory(cdc: str) -> CdcFactory:
        """Return the factory function for *cdc* (case-insensitive).

        Raises ``KeyError`` with a descriptive message if not found.
        """
        key = cdc.lower()
        try:
            return _REGISTRY[key]
        except KeyError:
            known = ", ".join(sorted(_REGISTRY))
            raise KeyError(f"Unknown CDC {cdc!r}. Known CDCs: {known}") from None

    @staticmethod
    def register(cdc: str, factory: CdcFactory) -> None:
        """Register a custom CDC factory (or override an existing one)."""
        _REGISTRY[cdc.lower()] = factory

    @staticmethod
    def known_cdcs() -> list[str]:
        return sorted(_REGISTRY)
