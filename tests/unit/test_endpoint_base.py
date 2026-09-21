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

"""Unit tests for base.py: WebSocketInfo and EndpointProtocol."""

from unittest.mock import MagicMock

import pytest

from ws61850.endpoint.base import EndpointProtocol, WebSocketInfo


class TestWebSocketInfo:
    def test_defaults(self):
        ws = MagicMock()
        info = WebSocketInfo(ws, "assoc-42")
        assert info.associate_id == "assoc-42"
        assert info.invoke_id == 0
        assert info.cp is None
        assert info.expiry_task is None
        assert info.access_token is None
        assert info.is_ber_protocol is False

    def test_cp_and_access_token(self):
        ws = MagicMock()
        info = WebSocketInfo(ws, "assoc-1", cp="cp1", access_token="tok")
        assert info.cp == "cp1"
        assert info.access_token == "tok"

    def test_websocket_reference(self):
        ws = MagicMock()
        info = WebSocketInfo(ws, "x")
        assert info.websocket is ws


class TestEndpointProtocol:
    def test_passive_endpoint_satisfies_protocol(self):
        from ws61850.endpoint.passive_endpoint import PassiveEndpoint

        ep = PassiveEndpoint()
        assert isinstance(ep, EndpointProtocol)

    def test_active_endpoint_satisfies_protocol(self):
        from ws61850.endpoint.active_endpoint import ActiveEndpoint

        ep = ActiveEndpoint()
        assert isinstance(ep, EndpointProtocol)


