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

import asyncio
import datetime
import logging

import websockets
import websockets.exceptions

from ws61850.security.oauth import get_access_token
from ws61850.asn1.encode_decode import decode_tpaa_message, encode_tpaa_message
from ws61850.endpoint.association_handler import (
    ACTION_ABORT,
    ACTION_RELEASE,
    AssociationHandler,
)
from ws61850.endpoint.base import WebSocketInfo
from ws61850.endpoint.connection_router import ConnectionRouter
from ws61850.iec61850.client.request_handling import create_tpaa_associate_request
from ws61850.shared.extractors import (
    extract_associate_request_type,
    retrieve_associate_id_from_decoded_msg,
    retrieve_max_outstanding_calls_from_decoded_msg,
)
from ws61850.security.tls import build_tls_context, build_tls_context_from_strings
from ws61850.transport.reconnect import ReconnectPolicy
from ws61850.security.oauth2.client_credentials import ClientCredentialsProvider

logger = logging.getLogger(__name__)


class ActiveEndpoint:
    """
    WebSocket client role: connects outward to a remote server and dispatches
    incoming messages to registered IEC 61850 server or client objects.

    When is_direct=True it uses client_list (sends associateRequest on connect).
    When is_direct=False it uses server_list (remote party initiates the association).
    """

    def __init__(
        self,
        *,
        tls_config=None,
        oauth_enable=False,
        is_direct=False,
        try_reconnect=True,
        max_retries=None,
        retry_connection_delay: float = 5.0,
        kc_cert=None,
        own_cert=None,
        cert_endpoint=None,
        token_issuer=None,
    ):
        self.server_list = []
        self.client_list = []
        self.websocket_info_list = []
        self.send_msg_callback = None
        self.recv_msg_callback = None
        self.server = None  # always None; property kept for EndpointProtocol compatibility

        self._tls_config = tls_config
        self._is_direct = is_direct

        self._reconnect_policy = ReconnectPolicy(
            enabled=try_reconnect,
            max_retries=max_retries,
            delay_seconds=retry_connection_delay,
        )
        self._oauth_enable = oauth_enable
        self._assoc_handler = AssociationHandler(
            kc_cert=kc_cert,
            own_cert=own_cert,
            cert_endpoint=cert_endpoint,
            token_issuer=token_issuer,
        )
        self._router = ConnectionRouter(self.server_list, self.client_list)

    # ------------------------------------------------------------------
    # Public interface (EndpointProtocol)
    # ------------------------------------------------------------------

    def add_iec61850_client(self, client) -> None:
        self.client_list.append(client)
        if self.send_msg_callback is not None:
            client.install_send_msg_callback(self.send_msg_callback)
        if self.recv_msg_callback is not None:
            client.install_recv_msg_callback(self.recv_msg_callback)

    def add_iec61850_server(self, server) -> None:
        self.server_list.append(server)
        if self.send_msg_callback is not None:
            server.install_send_msg_callback(self.send_msg_callback)
        if self.recv_msg_callback is not None:
            server.install_recv_msg_callback(self.recv_msg_callback)

    def get_websocket_info(self, iec61850_client) -> WebSocketInfo | None:
        return next(
            (
                ws_info
                for ws_info in self.websocket_info_list
                if ws_info.websocket.request.path.lstrip("/") == iec61850_client.cp
            ),
            None,
        )

    def get_websocket_info_iec61850_server(self, server) -> WebSocketInfo | None:
        return next(
            (
                ws_info
                for ws_info in self.websocket_info_list
                if ws_info.websocket.request.path.lstrip("/") == server.cp
            ),
            None,
        )
    async def reconfigure_connection(self,host, port, cp, tls_enable, tls_config=None):
        """Reconfigure TLS and OAuth settings for future connections."""
        self._tls_config = tls_config
        print("entering reconfigure_connection with tls_enable:", tls_enable)
        if tls_enable:
            print("entered reconfigure_connection with tls_enable True, tls_config:", tls_config)
            await self.start(host, int(port), cp)


    async def reconfigure_oauth(self, cp, oauth_enable, token_endpoint=None, client_id=None, client_secret=None, kc_cert=None, enable_token_refresh=False):
        """Reconfigure TLS and OAuth settings for future connections."""
        self._oauth_enable = oauth_enable
        self._assoc_handler._kc_cert = kc_cert
        self._assoc_handler._token_endpoint = token_endpoint

        client_con_provider: ClientCredentialsProvider = ClientCredentialsProvider(
            token_url=token_endpoint,
            client_id=client_id,
            client_secret=client_secret,
            cafile= kc_cert,
        )
        access_token = client_con_provider.get_access_token()
        if oauth_enable:
            await self.start("rti-so", 8765, cp, access_token= access_token)

    async def start(self, hostname: str, port: int, cp: str, *, access_token=None, protocol=None) -> None:
        """Connect to ws[s]://hostname:port/cp, with automatic reconnection."""
        self._reconnect_policy.reset()
        first = True
        while first or self._reconnect_policy.should_reconnect():
            first = False
            try:
                await self._connect_once(hostname, port, cp, access_token=access_token, protocol=protocol)
                self._reconnect_policy.reset()
            except (ConnectionRefusedError, OSError) as e:
                logger.warning("Connection failed cp=%r: %s", cp, e)
                await self._on_connection_closed(cp)
                if self._reconnect_policy.should_reconnect():
                    await self._reconnect_policy.wait()
                else:
                    logger.warning("Reconnection disabled or max retries reached for cp=%r, giving up", cp)
                    break
            except (websockets.exceptions.InvalidMessage, EOFError) as e:
                logger.warning("Connection failed cp=%r: protocol mismatch or server unavailable (%s)", cp, str(e).split('\n')[0])
                await self._on_connection_closed(cp)
                if self._reconnect_policy.should_reconnect():
                    await self._reconnect_policy.wait()
                else:
                    logger.warning("Reconnection disabled or max retries reached for cp=%r, giving up", cp)
                    break
            except Exception as e:
                logger.error("Unexpected error in active endpoint cp=%r: %s", cp, e, exc_info=True)
                await self._on_connection_closed(cp)
                if self._reconnect_policy.should_reconnect():
                    await self._reconnect_policy.wait()
                else:
                    break

    async def stop_passive(self) -> None:
        """No-op stub — ActiveEndpoint has no listening server to stop."""

    # ------------------------------------------------------------------
    # Internal session runner
    # ------------------------------------------------------------------

    async def _connect_once(self, hostname: str, port: int, cp: str, *, access_token=None, protocol=None) -> None:
        scheme = "wss" if self._tls_config else "ws"
        print("schema in fsp active endpoint _connect_once:", scheme)
        print(f"Connecting to {scheme}://{hostname}:{port}/{cp} with protocol={protocol}")
        uri = f"{scheme}://{hostname}:{int(port)}/{cp}"

        print("fsp is connecting with tls_config:", self._tls_config)
        print("fsp is connecting to uri: ", uri)

        connect_kwargs = dict(
            ssl=build_tls_context_from_strings(self._tls_config) if self._tls_config else None,
            subprotocols=protocol if protocol is not None else None,
            additional_headers={"Authorization": f"Bearer {access_token}"} if access_token else None,
            compression=None,
        )

        logger.info("Connecting to %s (protocol=%s)", uri, protocol)
        async with websockets.connect(uri, **connect_kwargs) as websocket:
            logger.info("WebSocket connection established to %s", uri)
            websocket_info = None

            try:
                if self._is_direct:
                    selected_client = self._router.find_client(cp)
                    if selected_client is not None:
                        logger.debug("Dispatching to client cp=%r (direct active mode)", cp)
                        self.websocket_info_list = [
                            ws_info
                            for ws_info in self.websocket_info_list
                            if ws_info.websocket.request.path.lstrip("/") != cp
                        ]
                        websocket_info = WebSocketInfo(websocket, "", cp=cp)
                        if protocol and "iec61850-tpaa-ber-v1" in protocol:
                            websocket_info.is_ber_protocol = True
                            logger.debug("BER encoding selected for cp=%r", cp)
                        self.websocket_info_list.append(websocket_info)

                        tpaa_request = create_tpaa_associate_request(selected_client.cp, 65000)
                        logger.debug("Sending associateRequest cp=%r", cp)
                        request = await asyncio.to_thread(
                            encode_tpaa_message, tpaa_request, websocket_info.is_ber_protocol
                        )
                        await websocket.send(request)
                        if self.send_msg_callback is not None:
                            self.send_msg_callback(request, datetime.datetime.now())

                        async for message in websocket:
                            if self.recv_msg_callback is not None:
                                self.recv_msg_callback(message, datetime.datetime.now())
                            else:
                                logger.info(
                                    "Received message: %s",
                                    decode_tpaa_message(message, websocket_info.is_ber_protocol),
                                )

                            if not selected_client.is_connected:
                                if not self._is_report(message, websocket_info.is_ber_protocol):
                                    decoded_message = await asyncio.to_thread(
                                        decode_tpaa_message, message, websocket_info.is_ber_protocol
                                    )
                                    if decoded_message[0] == "associate":
                                        associate_type = extract_associate_request_type(decoded_message)
                                        if associate_type == "associateResponse":
                                            asc_id = retrieve_associate_id_from_decoded_msg(decoded_message)
                                            max_calls = retrieve_max_outstanding_calls_from_decoded_msg(decoded_message)
                                            selected_client.max_outstanding_calls = max_calls
                                            websocket_info.associate_id = asc_id
                                            selected_client.is_connected = True
                                            selected_client.ready_event.set()
                                            logger.info(
                                                "Association established cp=%r associate_id=%r max_outstanding_calls=%s",
                                                cp,
                                                asc_id,
                                                max_calls,
                                            )
                            else:
                                if not self._is_report(message, websocket_info.is_ber_protocol):
                                    decoded_message = await asyncio.to_thread(
                                        decode_tpaa_message, message, websocket_info.is_ber_protocol
                                    )
                                    if decoded_message[0] == "associate":
                                        associate_type = extract_associate_request_type(decoded_message)
                                        logger.debug("Association control message cp=%r type=%r", cp, associate_type)
                                        action = await self._assoc_handler.handle(
                                            associate_type, decoded_message, websocket, websocket_info
                                        )
                                        if action in (ACTION_ABORT, ACTION_RELEASE):
                                            break

                                    invoke_id = selected_client.add_to_outstanding_calls(
                                        decoded_message, websocket_info.is_ber_protocol
                                    )
                                    if invoke_id and invoke_id > websocket_info.invoke_id:
                                        logger.warning(
                                            "Invoke ID out of sequence cp=%r invoke_id=%s expected<=%s, closing",
                                            cp,
                                            invoke_id,
                                            websocket_info.invoke_id,
                                        )
                                        await websocket.close()
                    else:
                        await self._router.send_not_found_response(
                            websocket, cp, protocol, self.send_msg_callback
                        )

                else:
                    selected_server = self._router.find_server(cp)
                    if selected_server is not None:
                        logger.debug("Dispatching to server cp=%r (non-direct active mode)", cp)
                        self.websocket_info_list = [
                            ws_info
                            for ws_info in self.websocket_info_list
                            if ws_info.websocket.request.path.lstrip("/") != cp
                        ]
                        websocket_info = WebSocketInfo(websocket, "", cp=cp)
                        if protocol and "iec61850-tpaa-ber-v1" in protocol:
                            websocket_info.is_ber_protocol = True
                            logger.debug("BER encoding selected for cp=%r", cp)
                        self.websocket_info_list.append(websocket_info)

                        async for message in websocket:
                            if self.recv_msg_callback is not None:
                                self.recv_msg_callback(message, datetime.datetime.now())

                            await selected_server.handle_request(message, cp, websocket_info)
                    else:
                        await self._router.send_not_found_response(
                            websocket, cp, protocol, self.send_msg_callback
                        )

            except websockets.exceptions.ConnectionClosedError as e:
                if "no close frame" in str(e):
                    logger.info("Connection aborted without close frame (likely via transport.abort())")
                else:
                    logger.info("Connection closed unexpectedly: code=%s, reason=%s", e.code, e.reason)

            except websockets.exceptions.ConnectionClosedOK:
                logger.info("Connection closed gracefully")

            except Exception as e:
                logger.exception("Unhandled error in active session: %s", e)

            finally:
                logger.info("Client disconnected: %s", websocket.remote_address)
                await self._on_connection_closed(cp)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_report(self, message: bytes, is_ber: bool) -> bool:
        decoded = decode_tpaa_message(message, is_ber)
        return decoded[0] == "unconfirmed"

    async def _on_connection_closed(self, cp: str) -> None:
        try:
            selected_client = self._router.find_client(cp)
            if selected_client:
                logger.info("clearing the client flags")
                selected_client.ready_event.clear()
                selected_client.is_connected = False
                selected_client.disconnect_event.set()

            #selected_server = self._router.find_server(cp)
            #if selected_server is not None:
                #selected_server.set_quality_to_questionable()
        except Exception as e:
            logger.error("Error in on_connection_closed: %s", e)
