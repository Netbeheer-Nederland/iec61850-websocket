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
Backward-compatible shim.

All new code should import PassiveEndpoint or ActiveEndpoint directly.
WebSocketEndpoint and WebSocketInfo remain here so that existing callers
(integration tests, examples, simulators) need zero changes.
"""

from ws61850.endpoint.active_endpoint import ActiveEndpoint
from ws61850.endpoint.base import WebSocketInfo  # re-export for callers
from ws61850.endpoint.passive_endpoint import PassiveEndpoint

__all__ = ["WebSocketEndpoint", "WebSocketInfo"]


class WebSocketEndpoint:
    """
    Deprecated buffering shim around PassiveEndpoint / ActiveEndpoint.

    Accepts all original constructor kwargs, buffers client/server registrations
    made before start(), then on start() constructs the right concrete endpoint,
    replays the buffered registrations, and delegates all subsequent calls.
    """

    def __init__(
        self,
        tls_config=None,
        is_direct=False,
        oauth_enable=False,
        try_reconnect=True,
        at_endpoint=None,
        at_endpoint_tls=None,
        kc_cert=None,
        own_cert=None,
        cert_endpoint=None,
        token_issuer=None,
    ):
        self._kwargs = dict(
            tls_config=tls_config,
            is_direct=is_direct,
            oauth_enable=oauth_enable,
            kc_cert=kc_cert,
            own_cert=own_cert,
            cert_endpoint=cert_endpoint,
            token_issuer=token_issuer,
        )
        self._active_kwargs = dict(
            try_reconnect=try_reconnect,
        )
        self._pending_clients = []
        self._pending_servers = []
        self._impl = None  # set in start()

        # Callbacks stored here pre-start, copied to impl in start()
        self.send_msg_callback = None
        self.recv_msg_callback = None

    # ------------------------------------------------------------------
    # Pre-start buffering of registrations
    # ------------------------------------------------------------------

    def add_iec61850_client(self, client):
        if self._impl is not None:
            self._impl.add_iec61850_client(client)
        else:
            self._pending_clients.append(("client", client))

    def add_iec61850_server(self, server):
        if self._impl is not None:
            self._impl.add_iec61850_server(server)
        else:
            self._pending_servers.append(("server", server))

    # ------------------------------------------------------------------
    # Bridged properties (safe defaults before start())
    # ------------------------------------------------------------------

    @property
    def websocket_info_list(self):
        return self._impl.websocket_info_list if self._impl else []

    @websocket_info_list.setter
    def websocket_info_list(self, value):
        if self._impl is not None:
            self._impl.websocket_info_list = value

    @property
    def server(self):
        return getattr(self._impl, "server", None)

    # ------------------------------------------------------------------
    # Delegation after start()
    # ------------------------------------------------------------------

    def get_websocket_info(self, iec61850_client):
        return self._impl.get_websocket_info(iec61850_client) if self._impl else None

    def get_websocket_info_iec61850_server(self, server):
        return self._impl.get_websocket_info_iec61850_server(server) if self._impl else None

    async def stop_passive(self):
        if self._impl is not None:
            await self._impl.stop_passive()

    async def start(self, mode, hostname, port, cp=None, access_token=None, protocol=None, *args):
        if mode == "passive":
            impl = PassiveEndpoint(**self._kwargs)
        elif mode == "active":
            impl = ActiveEndpoint(**self._kwargs, **self._active_kwargs)
        else:
            raise ValueError(f"Unknown mode: {mode!r}")

        impl.send_msg_callback = self.send_msg_callback
        impl.recv_msg_callback = self.recv_msg_callback

        for kind, obj in self._pending_clients:
            impl.add_iec61850_client(obj)
        for kind, obj in self._pending_servers:
            impl.add_iec61850_server(obj)

        self._impl = impl

        if mode == "passive":
            await impl.start(hostname, port, protocol)
        else:
            await impl.start(hostname, port, cp, access_token=access_token, protocol=protocol)
