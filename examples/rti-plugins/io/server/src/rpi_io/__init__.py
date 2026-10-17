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

"""The rti-demo's IO server for the Raspberry Pi: GPIO and I2C devices behind a
FastAPI REST API (python -m rpi_io.main). The role is "io". It is also the
FSP's and SO's IO plugin: they connect to it at /plugin (plugin.py, decision
0029). See decisions 0018, 0023 and 0029."""
