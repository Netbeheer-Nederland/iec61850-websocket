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

import logging

logger = logging.getLogger(__name__)


def print_node(index, item, last_index):
    """Prints an SDO node in the reconstructed tree."""
    sdo_prefix = "          ├── " if index != last_index - 1 else "          └── "
    logger.info(f"{sdo_prefix}{item}")


def print_node_da(index, item, last_index, go_to_next_level, is_structure):
    """Prints a data attribute node in the reconstructed tree."""
    if is_structure:
        sdo_prefix = "               └── "
    else:
        sdo_prefix = "               ├── " if index != last_index - 1 else "               └── "
    if go_to_next_level > 0:
        logger.info(go_to_next_level * "     " + f"{sdo_prefix}{item}")
    else:
        logger.info(f"{sdo_prefix}{item}")


def print_structure(structure_list, item_index, list_len, go_to_next_level):
    """Recursively prints structured items in the reconstructed tree."""
    for index, struct_item in enumerate(structure_list):
        cmp_type_key = next(iter(struct_item["cmpType"]))
        if cmp_type_key != "structure":
            print_node_da(index, struct_item["cmpName"], len(structure_list), go_to_next_level, False)
        else:
            print_node_da(item_index, struct_item["cmpName"], len(structure_list), go_to_next_level, True)
            struct_item = next(iter(struct_item["cmpType"].values()))
            print_structure(struct_item, index, len(struct_item), 2)


def print_direct_da(da_list):
    """Prints data attributes directly on a Data Object."""
    for da_index, da in enumerate(da_list):
        print_node_da(da_index, da["daRef"], len(da_list), 0, True)
        if next(iter(da["daType"])) == "structure":
            structure_list = next(iter(da["daType"].values()))
            print_structure(structure_list, da_index, len(da_list), 1)
