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

from typing import Callable, Protocol, runtime_checkable


class WebSocketInfo:
    """Per-connection session state shared between endpoint and IEC 61850 application layers."""

    def __init__(self, websocket, associate_id, cp=None, access_token=None):
        self.websocket = websocket
        self.associate_id = associate_id
        self.invoke_id = 0
        self.cp = cp
        self.expiry_task = None
        self.access_token = access_token
        self.is_ber_protocol: bool = False


@runtime_checkable
class EndpointProtocol(Protocol):
    """
    Structural interface implemented by both PassiveEndpoint and ActiveEndpoint.

    Bindings, transports, and runtime code should type-annotate against this
    rather than the concrete classes so they remain decoupled from the role.
    """

    websocket_info_list: list
    send_msg_callback: Callable | None
    recv_msg_callback: Callable | None
    server: object  # websockets Server | None

    def add_iec61850_client(self, client) -> None: ...
    def add_iec61850_server(self, server) -> None: ...
    def get_websocket_info(self, iec61850_client) -> WebSocketInfo | None: ...
    def get_websocket_info_iec61850_server(self, server) -> WebSocketInfo | None: ...
    async def start(self, *args, **kwargs) -> None: ...
    async def stop_passive(self) -> None: ...
