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
import sys
import time
from http import HTTPStatus

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Request, Response

from ws61850.iec61850.client.iec61850_client import IEC61850Client
from ws61850.asn1.encode_decode import decode_tpaa_message, encode_tpaa_message
from ws61850.endpoint.association_handler import (
    ACTION_ABORT,
    ACTION_RELEASE,
    AssociationHandler,
)
from ws61850.endpoint.base import WebSocketInfo
from ws61850.endpoint.connection_router import ConnectionRouter
from ws61850.iec61850.client.request_handling import create_tpaa_associate_request
from ws61850.security.oauth2.jwks import JwksCache
from ws61850.security.oauth2.validator import JwtValidator
from ws61850.security.tls import build_tls_context, build_tls_context_from_strings
from ws61850.shared.extractors import (
    extract_associate_request_type,
    retrieve_associate_id_from_decoded_msg,
    retrieve_max_outstanding_calls_from_decoded_msg,
)

import tempfile
import os

logger = logging.getLogger(__name__)


class _WebSocketServerLogger(logging.LoggerAdapter):
    """Downgrade expected handshake disconnects from error tracebacks to info logs."""

    def error(self, msg, *args, **kwargs):
        exc = kwargs.get("exc_info")
        if exc is True:
            exc = sys.exc_info()
        if isinstance(exc, tuple):
            exc = exc[1]

        if msg == "opening handshake failed" and isinstance(exc, EOFError) and "before end of line" in str(exc):
            self.logger.info("WebSocket peer disconnected before sending a handshake request")
            self.logger.debug("Handshake EOF while awaiting request line", exc_info=kwargs.get("exc_info"))
            return

        super().error(msg, *args, **kwargs)


class PassiveEndpoint:
    """
    WebSocket server role: listens for incoming connections and dispatches them
    to registered IEC 61850 server or client objects.

    When is_direct=True it serves server_list (field devices connect as WS clients).
    When is_direct=False it serves client_list (IEC 61850 clients connect and wait
    for a remote server to initiate the association).
    """

    def __init__(
        self,
        *,
        tls_config=None,
        oauth_enable=False,
        is_direct=False,
        kc_cert=None,
        own_cert=None,
        cert_endpoint=None,
        token_issuer=None,
    ):
        self.server_list = []
        self.client_list = []
        self.websocket_info_list = []
        self.access_token_list = []
        self.send_msg_callback = None
        self.recv_msg_callback = None
        self.server = None  # websockets.Server set in start()
        self._is_endpoint_running = False
        self._endpoint_running_event = asyncio.Event()

        self._tls_config = tls_config
        self._oauth_enable = oauth_enable
        self._is_direct = is_direct
        self._kc_cert = kc_cert
        self._own_cert = own_cert
        self._cert_endpoint = cert_endpoint
        self._token_issuer = token_issuer

        # Define close_on_expiry as a bound method that can be passed safely
        # We'll set it up after the object is fully initialized
        self._close_on_expiry_bound = lambda ws, exp: self._close_on_expiry_impl(ws, exp)
        
        self._assoc_handler = AssociationHandler(
            kc_cert=kc_cert,
            own_cert=own_cert,
            cert_endpoint=cert_endpoint,
            token_issuer=token_issuer,
            close_on_expiry_fn=self._close_on_expiry_bound,
        )
        self._router = ConnectionRouter(self.server_list, self.client_list)
        self._websocket_server_logger = _WebSocketServerLogger(
            logging.getLogger("websockets.server"), {}
        )

        if oauth_enable and cert_endpoint and token_issuer:
            _cache = JwksCache(jwks_uri=cert_endpoint, cafile=kc_cert)
            self._jwt_validator = JwtValidator(_cache, issuer=token_issuer, audience="account")
        else:
            self._jwt_validator = None

    # ------------------------------------------------------------------
    # Internal helpers (defined early to avoid reference issues)
    # ------------------------------------------------------------------
    async def _close_on_expiry_impl(self, websocket, exp_timestamp: int) -> None:
        """Implementation of close_on_expiry that can be safely referenced."""
        delay = exp_timestamp - int(time.time())
        if delay > 0:
            await asyncio.sleep(delay)
        await websocket.close(code=4401, reason="Token expired")

    # ------------------------------------------------------------------
    # Public interface (EndpointProtocol)
    # ------------------------------------------------------------------
    def get_endpoint_status(self):
        return self._is_endpoint_running

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

    async def reconfigure_oauth(self, oauth_enable, certificate_endpoint=None, token_issuer=None, kc_cert=None):
        self._oauth_enable = oauth_enable

        self._cert_endpoint = certificate_endpoint
        self._token_issuer = token_issuer

        cert_file = None

        try:
            # kc_cert contains the certificate CONTENT, not a filename
            if kc_cert:
                cert_file = tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".pem",
                    delete=False,
                )
                cert_file.write(kc_cert)
                cert_file.flush()
                cert_file.close()

                cafile = cert_file.name
            else:
                cafile = None

            self._kc_cert = cafile

            if oauth_enable and certificate_endpoint and token_issuer:
                _cache = JwksCache(jwks_uri=certificate_endpoint, cafile=cafile)
                self._jwt_validator = JwtValidator(_cache, issuer=token_issuer, audience="account")
            else:
                self._jwt_validator = None

            if oauth_enable:
                if self._is_endpoint_running:
                    try:
                        await asyncio.wait_for(self.stop_passive(), timeout=10.0)  # ← Add timeout
                    except asyncio.TimeoutError:
                        logger.warning("Server stop timed out, continuing reconfigure")
                # Start server in background without blocking
                logger.info("Starting WebSocket server with TLS on")
                self._server_task = asyncio.create_task(
                    self._run_server("0.0.0.0", 8765)
                )
        except Exception  as e:
            logger.error(f"Error during reconfigure_oauth: {e}", exc_info=True)
            raise


        #finally:
            # Remove the temporary certificate file
        #    if cert_file is not None:
        #        try:
        #            os.unlink(cert_file.name)
        #        except FileNotFoundError:
        #            pass

    async def reconfigure_endpoint(self, tls_enable, tls_config=None, oauth_enable=False):
        self._tls_config = tls_config
        self._oauth_enable = oauth_enable

        if tls_enable:
            if self._is_endpoint_running:
                try:
                    await asyncio.wait_for(self.stop_passive(), timeout=10.0)
                except Exception as e:
                    logger.error(f"stop_passive failed during reconfigure: {e}", exc_info=True)
                    raise RuntimeError(f"Cannot enable TLS: failed to stop existing server: {e}")

                if hasattr(self, '_server_task') and self._server_task and not self._server_task.done():
                    try:
                        await asyncio.wait_for(self._server_task, timeout=10.0)
                    except asyncio.CancelledError:
                        # Expected: closing the server cancels its serve_forever() future,
                        # which surfaces here as CancelledError. This means the old
                        # server shut down successfully, not that something failed.
                        logger.info("Old server task ended via close()-triggered cancellation (expected)")
                    except asyncio.TimeoutError:
                        logger.error("Old server task did not exit within timeout")
                        raise RuntimeError("Cannot enable TLS: port 8765 still in use (old task didn't exit)")

                # Wait for port to be released from TIME_WAIT state (critical on Windows)
                await asyncio.sleep(3.0)

            if not self._is_endpoint_running:
                logger.info("Starting WebSocket server with TLS on")
                self._server_task = asyncio.create_task(
                    self._run_server("0.0.0.0", 8765)
                )
            else:
                raise RuntimeError("Cannot start TLS server: old server still running")

    async def _run_server(self, hostname: str, port: int):
        """Internal method that actually runs the server."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self.start(hostname, port)
                return  # Success - exit
            except OSError as e:
                if e.errno in (98, 10048):  # Address already in use
                    delay = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(
                        f"Port {port} in use (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("Error running WebSocket server: %s", e, exc_info=True)
                    raise
        # If all retries fail
        raise RuntimeError(f"Failed to start server on {hostname}:{port} after {max_retries} attempts")


    async def start(self, hostname: str, port: int, protocol=None) -> None:
        ssl_ctx = build_tls_context_from_strings(self._tls_config) if self._tls_config else None
        scheme = "wss" if ssl_ctx else "ws"
        print("the scheme is: ", scheme)

        serve_kwargs = dict(
            subprotocols=protocol if protocol is not None else None,
            process_request=self.process_request,
            ping_interval=15,
            ping_timeout=30,
            logger=self._websocket_server_logger,
        )
        print("serve_kwargs: ", serve_kwargs)
        if ssl_ctx:
            serve_kwargs["ssl"] = ssl_ctx
        print("serve_kwargs after ssl: ", serve_kwargs)

        async with serve(self.handle_client, hostname, port, **serve_kwargs) as server:
            self.server = server
            self._is_endpoint_running = True
            self._endpoint_running_event.set()
            logger.info("WebSocket server started on %s://%s:%s", scheme, hostname, port)
            await server.serve_forever()

    async def stop_passive(self) -> None:
        try:
            if self.server is not None:
                self.server.close()
                try:
                    await self.server.wait_closed()
                except RuntimeError as e:
                    if "attached to a different loop" in str(e):
                        await asyncio.sleep(0.5)
                    else:
                        raise
                self._is_endpoint_running = False
                self._endpoint_running_event.clear()
                # Clear stale per-connection state so nothing carries loop-bound
                # asyncio primitives (Events/Locks) into the next server lifetime.
                self.client_list.clear()
                self.access_token_list.clear()
                self.websocket_info_list.clear()
                logger.info("WebSocket passive server stopped")
            else:
                logger.info("Passive server stop requested but server reference is None")
        except Exception as e:
            logger.error(f"Error stopping passive server: {e}")
            raise
    # ------------------------------------------------------------------
    # WebSocket callbacks
    # ------------------------------------------------------------------

    async def handle_client(self, websocket) -> None:
        path = websocket.request.path
        clean_path = path.lstrip("/")
        protocol = websocket.subprotocol

        logger.info(
            "Incoming WebSocket connection cp=%r peer=%s protocol=%s",
            clean_path,
            websocket.remote_address,
            protocol,
        )

        try:
            if self._is_direct:
                selected_server = self._router.find_server(clean_path)
                if selected_server is not None:
                    logger.debug("Dispatching to server cp=%r (direct mode)", clean_path)
                    selected_server.ready_event.set()
                    self.websocket_info_list = [
                        ws_info
                        for ws_info in self.websocket_info_list
                        if ws_info.websocket.request.path.lstrip("/") != clean_path
                    ]

                    websocket_info = WebSocketInfo(websocket, "", cp=clean_path)
                    if protocol and "iec61850-tpaa-ber-v1" in protocol:
                        websocket_info.is_ber_protocol = True
                        logger.debug("BER encoding selected for cp=%r", clean_path)
                    self.websocket_info_list.append(websocket_info)

                    if self._oauth_enable:
                        current_access_token = next(
                            (item for item in self.access_token_list if item["cp"] == clean_path),
                            None,
                        )
                        websocket_info.expiry_task = asyncio.create_task(
                            self._close_on_expiry_impl(websocket, current_access_token["access_token"]["exp"])
                        )
                        logger.debug("Token expiry task scheduled for cp=%r", clean_path)

                    async for message in websocket:
                        if self.recv_msg_callback is not None:
                            self.recv_msg_callback(message, datetime.datetime.now())
                        decoded_message = await asyncio.to_thread(
                            decode_tpaa_message, message, websocket_info.is_ber_protocol
                        )

                        if decoded_message[0] == "associate":
                            associate_type = extract_associate_request_type(decoded_message)
                            logger.debug("Association control message cp=%r type=%r", clean_path, associate_type)
                            action = await self._assoc_handler.handle(
                                associate_type, decoded_message, websocket, websocket_info
                            )
                            if action in (ACTION_ABORT, ACTION_RELEASE):
                                break

                        await selected_server.handle_request(message, clean_path, websocket_info)
                else:
                    await self._router.send_not_found_response(
                        websocket, clean_path, protocol, self.send_msg_callback
                    )

            else:
                selected_client = self._router.find_client(clean_path)
                if selected_client is not None:
                    logger.debug("Dispatching to client cp=%r (passive mode)", clean_path)
                    self.websocket_info_list = [
                        ws_info
                        for ws_info in self.websocket_info_list
                        if ws_info.websocket.request.path.lstrip("/") != clean_path
                    ]
                    websocket_info = WebSocketInfo(websocket, "", cp=clean_path)
                    if protocol and "iec61850-tpaa-ber-v1" == protocol:
                        websocket_info.is_ber_protocol = True
                        logger.debug("BER encoding selected for cp=%r", clean_path)
                    self.websocket_info_list.append(websocket_info)

                    if self._oauth_enable:
                        current_access_token = next(
                            (item for item in self.access_token_list if item["cp"] == clean_path),
                            None,
                        )
                        websocket_info.expiry_task = asyncio.create_task(
                            self._close_on_expiry_impl(websocket, current_access_token["access_token"]["exp"])
                        )
                        logger.debug("Token expiry task scheduled for cp=%r", clean_path)

                    tpaa_request = create_tpaa_associate_request(selected_client.cp, 65000)
                    logger.debug("Sending associateRequest to remote server cp=%r", clean_path)
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
                            logger.info("Received message: %s", message)

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
                                            clean_path,
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
                                    logger.debug("Association control message cp=%r type=%r", clean_path, associate_type)
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
                                        clean_path,
                                        invoke_id,
                                        websocket_info.invoke_id,
                                    )
                                    await websocket.close()
                else:
                    await self._router.send_not_found_response(
                        websocket, clean_path, protocol, self.send_msg_callback
                    )

        except Exception as e:
            logger.error("Error in server handler function cp=%r: %s", clean_path, e, exc_info=True)

        finally:
            await websocket.wait_closed()
            logger.info("Client disconnected: %s cp=%r", websocket.remote_address, clean_path)
            await self._on_connection_closed(clean_path)

    async def process_request(self, connection, request: Request):
        cp = connection.request.path.lstrip("/")
        headers = request.headers
        auth_header = headers.get("Authorization")

        self.client_list[:] = [c for c in self.client_list if c.cp != cp]
        self.client_list.append(IEC61850Client(cp))
        if self._oauth_enable:
            if not auth_header or not auth_header.startswith("Bearer "):
                logger.warning("OAuth: missing or malformed Authorization header for cp=%r", cp)
                return self._http_error_response(HTTPStatus.UNAUTHORIZED, b"Missing or invalid token\n")
            token = auth_header[len("Bearer "):]
            if self._jwt_validator is None:
                logger.error("OAuth: JWT validator not configured but oauth_enable=True for cp=%r", cp)
                return self._http_error_response(
                    HTTPStatus.SERVICE_UNAVAILABLE, b"Token verification unavailable\n"
                )
            try:
                is_valid, claims = self._jwt_validator.validate(token)
            except (KeyError, Exception) as e:
                logger.error("OAuth: JWKS fetch or decode error for cp=%r: %s", cp, e)
                return self._http_error_response(
                    HTTPStatus.SERVICE_UNAVAILABLE, b"Token verification unavailable\n"
                )
            if not is_valid or claims is None:
                logger.warning("OAuth: token rejected (invalid or expired) for cp=%r", cp)
                return self._http_error_response(HTTPStatus.UNAUTHORIZED, b"Invalid or expired token\n")
            logger.info("OAuth: token accepted for cp=%r expires_at=%s", cp, claims.expiry)
            # Replace any stale entry for this cp so handle_client always sees
            # the token that was just validated for THIS connection attempt,
            # not a leftover from an earlier one.
            self.access_token_list = [item for item in self.access_token_list if item["cp"] != cp]
            self.access_token_list.append(
                {"access_token": {"exp": claims.expiry}, "cp": cp, "access_token_raw": token}
            )
            return None
        else:
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_report(self, message: bytes, is_ber: bool) -> bool:
        decoded = decode_tpaa_message(message, is_ber)
        return decoded[0] == "unconfirmed"

    async def _on_connection_closed(self, cp: str) -> None:
        try:
            selected_server = self._router.find_server(cp)
            selected_client = self._router.find_client(cp)
            if selected_client:
                logger.info("clearing the client flags")
                selected_client.ready_event.clear()
                selected_client.is_connected = False
                selected_client.disconnect_event.set()
            if selected_server is not None:
                selected_server.set_quality_to_questionable()
        except Exception as e:
            logger.error("Error in on_connection_closed: %s", e)

    @staticmethod
    def _http_error_response(status: HTTPStatus, body: bytes) -> Response:
        headers = Headers()
        headers["Content-Type"] = "text/plain; charset=utf-8"
        headers["Content-Length"] = str(len(body))
        headers["Connection"] = "close"
        return Response(status.value, status.phrase, headers, body)
