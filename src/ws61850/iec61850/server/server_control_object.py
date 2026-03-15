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

from ws61850.iec61850.data_model.ied_model import FunctionalConstraint, IedModel


class ServerControlObject:
    def __init__(self, data_object):
        self.data_object = data_object
        self.is_selected = False


def get_control_das(data_object, list):
    control_item = next((da for da in data_object.get_da_from_do_or_da_list() if da.fc == FunctionalConstraint.co),
                        None)
    if control_item is not None:
        list.append(ServerControlObject(data_object))
    if len(data_object.get_do_from_do_or_da_list()) > 0:
        for sdo in data_object.get_do_from_do_or_da_list():
            get_control_das(sdo, list)


def create_server_control_objects_list(ied: IedModel):
    control_object_list = []
    for ld in ied.logical_devices:
        for ln in ld.logical_nodes:
            for do in ln.data_objects:
                get_control_das(do, control_object_list)

    return control_object_list
