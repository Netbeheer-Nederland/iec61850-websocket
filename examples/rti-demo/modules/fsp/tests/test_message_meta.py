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

"""ACSIServer._extract_message_meta - how the FSP labels a logged frame."""

from __future__ import annotations

from fsp.acsi_server import ACSIServer


def _server():
    # _extract_message_meta uses no instance state - skip loading a model.
    return object.__new__(ACSIServer)


def test_report_carries_its_cp():
    raw = '{"unconfirmed": {"associateId": "cp2", "service": {"report": {"rptID": "ActualValues"}}}}'

    assert _server()._extract_message_meta(raw) == {
        "service_type": "report",
        "category": "unconfirmed",
        "cp": "cp2",
        "invoke_id": None,
    }


def test_request_carries_cp_and_invoke_id():
    raw = '{"request": {"associateId": "cp1", "invokeId": 3, "service": {"getDataValues": {}}}}'

    assert _server()._extract_message_meta(raw) == {
        "service_type": "getDataValues",
        "category": "request",
        "cp": "cp1",
        "invoke_id": 3,
    }
