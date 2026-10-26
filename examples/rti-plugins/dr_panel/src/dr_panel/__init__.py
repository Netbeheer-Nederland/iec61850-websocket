# SPDX-FileCopyrightText: 2025-2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025-2026 Netbeheer Nederland
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

"""The rti-demo's IO plugin for the Raspberry Pi (decisions 0018, 0029, 0030, 0038).

- dr_panel.server: the IO server, GPIO and I2C devices behind the REST API
  /api/io (python -m dr_panel.server.main, or the script dr-panel). The role is "io";
  the plugin name "dr_panel" (decision 0040).
- dr_panel.plugin: the plugin API under /plugin, which the FSP and SO connect
  to, and io_mapping.json, which says what the devices show.
"""
