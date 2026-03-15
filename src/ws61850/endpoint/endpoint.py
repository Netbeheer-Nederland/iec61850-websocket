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
import time
from http import HTTPStatus

import jwt
import requests
import websockets
from jwt import (
    ExpiredSignatureError,
    InvalidTokenError,
    PyJWKClient,
    algorithms,
    decode,
)
from websockets.asyncio.server import serve

from ws61850.asn1.encode_decode import decode_tpaa_message, encode_tpaa_message
from ws61850.iec61850.client.request_handling import create_tpaa_associate_request
from ws61850.iec61850.server.request_handling import (
    extract_associate_request_type,
    retrieve_associate_id_from_decoded_msg,
    retrieve_max_outstanding_calls_from_decoded_msg,
)
from ws61850.iec61850.server.response_handling import (
    create_tpaa_abort_response,
    create_tpaa_associate_response,
    create_tpaa_release_response,
)
from ws61850.iec61850.server.service_error import ServiceStatusKind
from ws61850.security.oauth import check_token_validity_and_expiry, get_jwt_algorithm

logger = logging.getLogger(__name__)

max_message_size = 65000
max_message_size_server = 65000


class WebSocketInfo:
    def __init__(self, websocket, associate_id, cp=None, access_token=None):
        self.websocket = websocket
        self.associate_id = associate_id
        self.invoke_id = 0
        self.cp = cp
        self.expiry_task = None
        self.access_token = access_token
        self.is_ber_protocol = False


class WebSocketEndpoint:
    """
    Class to represent a websocket endpoint
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
        """
        Initializing function
        """
        # self.id = id
        self.server_list = []
        self.client_list = []
        self.mode = None
        self.websocket_info_list = []
        self.incoming_queue = asyncio.Queue()
        self.is_direct = is_direct
        self.access_token_list = []
        self.tls_config = tls_config
        self.send_msg_callback = None
        self.recv_msg_callback = None
        self.try_reconnect = try_reconnect
        self.max_retries = None
        self.retry_connection_delay = 5
        self.oauth_enable = oauth_enable
        # Passive server reference (websockets.server.Server) set in __start_passive
        self.server = None

        self.oauth_enable = oauth_enable
        self.at_endpoint = at_endpoint
        self.at_endpoint_tls = at_endpoint_tls
        self.kc_cert = kc_cert
        self.own_cert = own_cert
        self.cert_endpoint = cert_endpoint
        self.token_issuer = token_issuer

    def if_message_is_report(self, message):
        import json

        data = json.loads(message)
        top_key = next(iter(data))  # gets the first key from the dict
        if top_key == "unconfirmed":
            return True
        else:
            return False

    async def stop_passive(self):
        """Gracefully stop passive websocket server if running."""
        try:
            if self.server is not None:
                self.server.close()
                await self.server.wait_closed()
                logger.info("WebSocket passive server stopped")
            else:
                logger.info("Passive server stop requested but server reference is None")
        except Exception as e:
            logger.error(f"Error stopping passive server: {e}")

    async def on_connection_closed(
        self,
        websocket,
        clean_path,
        is_ws_client=False,
        hostname=None,
        port=None,
        protocol=None,
    ):
        try:
            selected_server = next((server for server in self.server_list if server.cp == clean_path), None)

            selected_client = next((client for client in self.client_list if client.cp == clean_path), None)
            if selected_client:
                logger.info("clearing the client flags")
                selected_client.ready_event.clear()  # <-- Reset event so main() can wait again
                selected_client.is_connected = False
                selected_client.disconnect_event.set()

            if selected_server is not None:
                selected_server.set_quality_to_questionable()

        except Exception as e:
            logger.error(f"error{e}")

        if is_ws_client:
            attempt = 0

            while self.try_reconnect:
                try:
                    self.websocket_info_list = [
                        ws_info
                        for ws_info in self.websocket_info_list
                        if ws_info.websocket.request.path.lstrip("/") != clean_path
                    ]
                    try:
                        await websocket.close()
                    except Exception:
                        pass
                    await self.__start_active(hostname, port, clean_path, protocol)
                    break
                except (ConnectionRefusedError, OSError) as e:
                    attempt += 1
                    logger.warning(f"Connection failed: {e}")
                    if self.max_retries and attempt >= self.max_retries:
                        logger.warning(" Max retries reached. Giving up.")
                        return
                    logger.warning(f"Retrying in {self.retry_connection_delay} seconds...")
                    await asyncio.sleep(self.retry_connection_delay)
                except Exception as e:
                    logger.error(f"Unexpected error: {e}")
                    await asyncio.sleep(self.retry_connection_delay)

    async def close_on_expiry(self, websocket, exp_timestamp):
        """Closes the connection when the token expires."""
        delay = exp_timestamp - int(time.time())
        if delay > 0:
            await asyncio.sleep(delay)
        await websocket.close(code=4401, reason="Token expired")

    async def handle_client(self, websocket):
        """
        Websocket server handing function
        """
        path = websocket.request.path
        clean_path = path.lstrip("/")

        protocol = websocket.subprotocol
        try:
            if self.is_direct:
                selected_server = next(
                    (server for server in self.server_list if server.cp == clean_path),
                    None,
                )
                # selected_server.install_send_msg_callback(self.send_msg_callback)
                if selected_server is not None:
                    selected_server.ready_event.set()
                    self.websocket_info_list = [
                        ws_info
                        for ws_info in self.websocket_info_list
                        if ws_info.websocket.request.path.lstrip("/") != clean_path
                    ]

                    websocket_info = WebSocketInfo(websocket, "", cp=clean_path)
                    if protocol:
                        if "iec61850-tpaa-ber-v1" in protocol:
                            websocket_info.is_ber_protocol = True

                    self.websocket_info_list.append(websocket_info)

                    if self.oauth_enable:
                        current_access_token = next(
                            (item for item in self.access_token_list if item["cp"] == clean_path),
                            None,
                        )
                        websocket_info.expiry_task = asyncio.create_task(
                            self.close_on_expiry(websocket, current_access_token["access_token"]["exp"])
                        )

                    async for message in websocket:
                        # logger.info(f"Received from websocket server (IEC61850 client): {message}")
                        if self.recv_msg_callback is not None:
                            self.recv_msg_callback(message, datetime.datetime.now())
                        # else:
                        #    logger.info(f"Received message: {message}")
                        # logger.info(f"Received message: {decode_tpaa_message(message, websocket_info.is_ber_protocol)}")
                        decoded_message = await asyncio.to_thread(
                            decode_tpaa_message, message, websocket_info.is_ber_protocol
                        )

                        if decoded_message[0] == "associate":
                            associate_type = extract_associate_request_type(decoded_message)
                            if associate_type == "abortRequest":
                                tpaa_request = create_tpaa_abort_response(
                                    websocket_info.invoke_id,
                                    websocket_info.associate_id,
                                )
                                # request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
                                request = await asyncio.to_thread(
                                    encode_tpaa_message,
                                    tpaa_request,
                                    websocket_info.is_ber_protocol,
                                )
                                await websocket.send(request)
                                websocket.transport.abort()
                                logger.info("Association aborted by server")
                                break
                            elif associate_type == "releaseRequest":
                                tpaa_request = create_tpaa_release_response(
                                    websocket_info.invoke_id,
                                    websocket_info.associate_id,
                                )
                                # request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
                                request = await asyncio.to_thread(
                                    encode_tpaa_message,
                                    tpaa_request,
                                    websocket_info.is_ber_protocol,
                                )
                                await websocket.send(request)
                                await websocket.close()
                                logger.info("Association released by server")
                                break
                            elif associate_type == "refreshToken":
                                validity, expiry = check_token_validity_and_expiry(
                                    decoded_message[1][1][1]["token"],
                                    self.kc_cert,
                                    self.own_cert,
                                    self.cert_endpoint,
                                    self.token_issuer,
                                )
                                if validity is True and expiry is not None:
                                    websocket_info.expiry_task.cancel()
                                    try:
                                        await websocket_info.expiry_task
                                    except asyncio.CancelledError:
                                        pass

                                    websocket_info.expiry_task = asyncio.create_task(
                                        self.close_on_expiry(websocket, expiry)
                                    )

                        await selected_server.handle_request(message, clean_path, websocket_info)
                else:
                    tpaa_request = create_tpaa_associate_response(
                        65000, clean_path, ServiceStatusKind.instanceNotAvailable.name
                    )
                    is_ber = False
                    if protocol:
                        if "iec61850-tpaa-ber-v1" == protocol:
                            is_ber = True

                    # request = encode_tpaa_message(tpaa_request, is_ber)
                    request = await asyncio.to_thread(encode_tpaa_message, tpaa_request, is_ber)
                    await websocket.send(request)
                    if self.send_msg_callback is not None:
                        self.send_msg_callback(request, datetime.datetime.now())
                    logger.info("Connection failed: Access Point not available")
                    await websocket.close()

            else:
                selected_client = next(
                    (client for client in self.client_list if client.cp == clean_path),
                    None,
                )
                if selected_client is not None:
                    self.websocket_info_list = [
                        ws_info
                        for ws_info in self.websocket_info_list
                        if ws_info.websocket.request.path.lstrip("/") != clean_path
                    ]
                    websocket_info = WebSocketInfo(websocket, "", cp=clean_path)
                    if protocol:
                        if "iec61850-tpaa-ber-v1" == protocol:
                            websocket_info.is_ber_protocol = True

                    self.websocket_info_list.append(websocket_info)

                    if self.oauth_enable:
                        current_access_token = next(
                            (item for item in self.access_token_list if item["cp"] == clean_path),
                            None,
                        )
                        websocket_info.expiry_task = asyncio.create_task(
                            self.close_on_expiry(websocket, current_access_token["access_token"]["exp"])
                        )

                    tpaa_request = create_tpaa_associate_request(selected_client.cp, 65000)
                    request = await asyncio.to_thread(
                        encode_tpaa_message,
                        tpaa_request,
                        websocket_info.is_ber_protocol,
                    )
                    # request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
                    await websocket.send(request)
                    if self.send_msg_callback is not None:
                        self.send_msg_callback(request, datetime.datetime.now())

                    async for message in websocket:
                        # logger.info("message in receiver: ", message)
                        if self.recv_msg_callback is not None:
                            self.recv_msg_callback(message, datetime.datetime.now())
                        else:
                            logger.info(f"Received message: {message}")
                            # logger.info(f"Received message: {decode_tpaa_message(message, websocket_info.is_ber_protocol)}")
                        if not selected_client.is_connected:
                            if not self.if_message_is_report(message):
                                decoded_message = await asyncio.to_thread(
                                    decode_tpaa_message,
                                    message,
                                    websocket_info.is_ber_protocol,
                                )

                                # decoded_message = decode_tpaa_message(message, websocket_info.is_ber_protocol)

                                if decoded_message[0] == "associate":
                                    associate_type = extract_associate_request_type(decoded_message)
                                    if associate_type == "associateResponse":
                                        asc_id = retrieve_associate_id_from_decoded_msg(decoded_message)
                                        max_outstanding_calls = retrieve_max_outstanding_calls_from_decoded_msg(
                                            decoded_message
                                        )
                                        selected_client.max_outstanding_calls = max_outstanding_calls
                                        websocket_info.associate_id = asc_id
                                        selected_client.is_connected = True
                                        selected_client.ready_event.set()

                        else:
                            if not self.if_message_is_report(message):
                                decoded_message = await asyncio.to_thread(
                                    decode_tpaa_message,
                                    message,
                                    websocket_info.is_ber_protocol,
                                )
                                # decoded_message = decode_tpaa_message(message, websocket_info.is_ber_protocol)
                                if decoded_message[0] == "associate":
                                    associate_type = extract_associate_request_type(decoded_message)
                                    if associate_type == "abortRequest":
                                        tpaa_request = create_tpaa_abort_response(
                                            websocket_info.invoke_id,
                                            websocket_info.associate_id,
                                        )
                                        # request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
                                        request = await asyncio.to_thread(
                                            encode_tpaa_message,
                                            tpaa_request,
                                            websocket_info.is_ber_protocol,
                                        )
                                        await websocket.send(request)
                                        websocket.transport.abort()
                                        logger.info("Association aborted by server")
                                        break
                                    elif associate_type == "releaseRequest":
                                        tpaa_request = create_tpaa_release_response(
                                            websocket_info.invoke_id,
                                            websocket_info.associate_id,
                                        )
                                        # request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
                                        request = await asyncio.to_thread(
                                            encode_tpaa_message,
                                            tpaa_request,
                                            websocket_info.is_ber_protocol,
                                        )
                                        await websocket.send(request)
                                        await websocket.close()
                                        logger.info("Association released by server")
                                        break
                                    elif associate_type == "refreshToken":
                                        validity, expiry = check_token_validity_and_expiry(
                                            decoded_message[1][1][1]["token"],
                                            self.kc_cert,
                                            self.own_cert,
                                            self.cert_endpoint,
                                            self.token_issuer,
                                        )
                                        if validity is True and expiry is not None:
                                            websocket_info.expiry_task.cancel()
                                            try:
                                                await websocket_info.expiry_task
                                            except asyncio.CancelledError:
                                                pass

                                            websocket_info.expiry_task = asyncio.create_task(
                                                self.close_on_expiry(websocket, expiry)
                                            )

                                invoke_id = selected_client.add_to_outstanding_calls(
                                    decoded_message, websocket_info.is_ber_protocol
                                )
                                if invoke_id and invoke_id > websocket_info.invoke_id:
                                    logger.info("invoke id invalid, closing the connection ...")
                                    await websocket.close()

                else:
                    tpaa_request = create_tpaa_associate_response(
                        65000, clean_path, ServiceStatusKind.instanceNotAvailable.name
                    )
                    is_ber = False
                    if protocol:
                        if "iec61850-tpaa-ber-v1" in protocol:
                            is_ber = True

                    # request = encode_tpaa_message(tpaa_request, is_ber)
                    request = await asyncio.to_thread(encode_tpaa_message, tpaa_request, is_ber)
                    await websocket.send(request)
                    if self.send_msg_callback is not None:
                        self.send_msg_callback(request, datetime.datetime.now())
                    logger.info("Connection failed: access point not available")
                    await websocket.close()
        except Exception as e:
            logger.error(f"Error in server handler function: {e}")

        finally:
            await websocket.wait_closed()

            logger.info(f"Client disconnected: {websocket.remote_address}")

            await self.on_connection_closed(websocket, clean_path)

    async def process_request(self, path, request_headers):
        headers = request_headers.headers
        auth_header = headers.get("Authorization")

        if auth_header:
            token = auth_header[len("Bearer ") :]

            session = requests.Session()
            # session.cert = ("/home/raspberry/Desktop/rti2_protocol_spec/exploration/certs/server_ws.crt",
            #            "/home/raspberry/Desktop/rti2_protocol_spec/exploration/certs/server_ws.key" )
            # jwks_url = "https://localhost:8443/realms/master/protocol/openid-connect/certs"
            jwks_url = self.cert_endpoint
            session.verify = self.kc_cert
            response = session.get(jwks_url)

            jwks_data = response.json()
            jwks_client = PyJWKClient("https://dummy-url")
            jwks_client._jwks_data = jwks_data
            header = jwt.get_unverified_header(token)  # Extract 'kid' from token
            kid = header["kid"]
            jwk = next(key for key in jwks_data["keys"] if key["kid"] == kid)
            signing_key = algorithms.RSAAlgorithm.from_jwk(jwk)

            try:
                decoded = decode(
                    token,
                    signing_key,
                    algorithms=[get_jwt_algorithm(token)],
                    audience="account",
                    issuer=self.token_issuer,
                )

                self.access_token_list.append(
                    {
                        "access_token": decoded,
                        "cp": path.request.path.lstrip("/"),
                        "access_token_raw": token,
                    }
                )

            except ExpiredSignatureError:
                logger.warning("Token has expired")
                return HTTPStatus.FORBIDDEN, [], b"Expired token\n"

            except InvalidTokenError as e:
                logger.warning("Invalid token:", e)
                return HTTPStatus.FORBIDDEN, [], b"Invalid token\n"
        else:
            return HTTPStatus.UNAUTHORIZED, [], b"Missing or invalid token\n"

    async def start(self, mode, hostname, port, cp=None, access_token=None, protocol=None, *arg):
        if mode == "passive":
            await self.__start_passive(hostname, port, protocol)
        elif mode == "active":
            await self.__start_active(hostname, port, cp, protocol, access_token)

    async def __start_passive(self, hostname, port, protocol=None):
        """
        Function used for starting a websocket server
        """
        if self.tls_config is not None:
            async with serve(
                self.handle_client,
                hostname,
                port,
                ssl=self.tls_config.ssl_context,
                subprotocols=protocol if protocol else None,
                process_request=self.process_request if self.oauth_enable else None,
                ping_interval=15,
                ping_timeout=30,
            ) as server:
                logger.info(f"WebSocket server started on wss://{hostname}:{port}")
                await server.serve_forever()
        else:
            async with serve(
                self.handle_client,
                hostname,
                port,
                subprotocols=protocol if protocol is not None else None,
                process_request=self.process_request if self.oauth_enable else None,
                ping_interval=15,
                ping_timeout=30,
            ) as server:
                self.server = server
                logger.info(f"WebSocket server started on ws://{hostname}:{port}")
                await server.serve_forever()

    async def __start_active(self, url, port, cp, protocol=None, access_token=None):
        """
        Function used for starting the websocket client
        """
        uri = f"ws://{url}:{int(port)}/{cp}"
        if self.tls_config is not None:
            uri = f"wss://{url}:{int(port)}/{cp}"

        async with websockets.connect(
            uri,
            ssl=self.tls_config.ssl_context if self.tls_config else None,
            subprotocols=protocol if protocol is not None else None,
            additional_headers={"Authorization": f"Bearer {access_token}"} if access_token else None,
            compression=None,
        ) as websocket:
            logger.info(f"Started client connection to {uri}")
            websocket_info = None

            try:
                if self.is_direct:
                    selected_client = next((client for client in self.client_list if client.cp == cp), None)
                    if selected_client is not None:
                        self.websocket_info_list = [
                            ws_info
                            for ws_info in self.websocket_info_list
                            if ws_info.websocket.request.path.lstrip("/") != cp
                        ]
                        websocket_info = WebSocketInfo(websocket, "", cp=cp)
                        if protocol:
                            if "iec61850-tpaa-ber-v1" in protocol:
                                websocket_info.is_ber_protocol = True

                        self.websocket_info_list.append(websocket_info)

                        # if self.oauth_enable:
                        #     current_access_token = next(
                        #         (item for item in self.access_token_list if item["cp"] == cp), None)
                        #     websocket_info.expiry_task = asyncio.create_task(
                        #         self.close_on_expiry(websocket, current_access_token["access_token"]["exp"]))

                        tpaa_request = create_tpaa_associate_request(selected_client.cp, 65000)
                        request = await asyncio.to_thread(
                            encode_tpaa_message,
                            tpaa_request,
                            websocket_info.is_ber_protocol,
                        )
                        # request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
                        await websocket.send(request)
                        if self.send_msg_callback is not None:
                            self.send_msg_callback(request, datetime.datetime.now())

                        async for message in websocket:
                            if self.recv_msg_callback is not None:
                                self.recv_msg_callback(message, datetime.datetime.now())
                            else:
                                logger.info(
                                    f"Received message: {decode_tpaa_message(message, websocket_info.is_ber_protocol)}"
                                )
                            if not selected_client.is_connected:
                                if not self.if_message_is_report(message):
                                    decoded_message = await asyncio.to_thread(
                                        decode_tpaa_message,
                                        message,
                                        websocket_info.is_ber_protocol,
                                    )

                                    # decoded_message = decode_tpaa_message(message, websocket_info.is_ber_protocol)
                                    if decoded_message[0] == "associate":
                                        associate_type = extract_associate_request_type(decoded_message)
                                        if associate_type == "associateResponse":
                                            asc_id = retrieve_associate_id_from_decoded_msg(decoded_message)
                                            max_outstanding_calls = retrieve_max_outstanding_calls_from_decoded_msg(
                                                decoded_message
                                            )
                                            selected_client.max_outstanding_calls = max_outstanding_calls
                                            websocket_info.associate_id = asc_id
                                            selected_client.is_connected = True
                                            selected_client.ready_event.set()

                            else:
                                if not self.if_message_is_report(message):
                                    decoded_message = await asyncio.to_thread(
                                        decode_tpaa_message,
                                        message,
                                        websocket_info.is_ber_protocol,
                                    )

                                    # decoded_message = decode_tpaa_message(message, websocket_info.is_ber_protocol)
                                    if decoded_message[0] == "associate":
                                        associate_type = extract_associate_request_type(decoded_message)
                                        if associate_type == "abortRequest":
                                            tpaa_request = create_tpaa_abort_response(
                                                websocket_info.invoke_id,
                                                websocket_info.associate_id,
                                            )
                                            # request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
                                            request = await asyncio.to_thread(
                                                encode_tpaa_message,
                                                tpaa_request,
                                                websocket_info.is_ber_protocol,
                                            )
                                            await websocket.send(request)
                                            websocket.transport.abort()
                                            logger.info("Association aborted by server")
                                            break
                                        elif associate_type == "releaseRequest":
                                            tpaa_request = create_tpaa_release_response(
                                                websocket_info.invoke_id,
                                                websocket_info.associate_id,
                                            )
                                            # request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
                                            request = await asyncio.to_thread(
                                                encode_tpaa_message,
                                                tpaa_request,
                                                websocket_info.is_ber_protocol,
                                            )
                                            await websocket.send(request)
                                            await websocket.close()
                                            logger.info("Association released by server")
                                            break
                                        elif associate_type == "refreshToken":
                                            validity, expiry = check_token_validity_and_expiry(
                                                decoded_message[1][1][1]["token"],
                                                self.kc_cert,
                                                self.own_cert,
                                                self.cert_endpoint,
                                                self.token_issuer,
                                            )
                                            if validity is True and expiry is not None:
                                                websocket_info.expiry_task.cancel()
                                                try:
                                                    await websocket_info.expiry_task
                                                except asyncio.CancelledError:
                                                    pass

                                                websocket_info.expiry_task = asyncio.create_task(
                                                    self.close_on_expiry(websocket, expiry)
                                                )

                                    invoke_id = selected_client.add_to_outstanding_calls(
                                        decoded_message,
                                        websocket_info.is_ber_protocol,
                                    )
                                    if invoke_id and invoke_id > websocket_info.invoke_id:
                                        logger.info("invoke id invalid, closing the connection ...")
                                        await websocket.close()
                    else:
                        tpaa_request = create_tpaa_associate_response(
                            65000, cp, ServiceStatusKind.instanceNotAvailable.name
                        )
                        # request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
                        is_ber = False
                        if protocol:
                            if "iec61850-tpaa-ber-v1" in protocol:
                                websocket_info.is_ber_protocol = True

                        request = await asyncio.to_thread(encode_tpaa_message, tpaa_request, is_ber)
                        await websocket.send(request)
                        if self.send_msg_callback is not None:
                            self.send_msg_callback(request, datetime.datetime.now())
                        logger.info("Connection failed: access point not available")
                        await websocket.close()

                else:
                    selected_server = next((server for server in self.server_list if server.cp == cp), None)
                    if selected_server is not None:
                        ied = selected_server.ied_model
                        self.websocket_info_list = [
                            ws_info
                            for ws_info in self.websocket_info_list
                            if ws_info.websocket.request.path.lstrip("/") != cp  # or cp for __start_active
                        ]
                        websocket_info = WebSocketInfo(websocket, "", cp=cp)

                        if protocol:
                            if "iec61850-tpaa-ber-v1" in protocol:
                                websocket_info.is_ber_protocol = True

                        self.websocket_info_list.append(websocket_info)

                        async for message in websocket:
                            if self.recv_msg_callback is not None:
                                self.recv_msg_callback(message, datetime.datetime.now())
                            # else:
                            #    logger.info(f"Received message: {decode_tpaa_message(message, websocket_info.is_ber_protocol)}")

                            await selected_server.handle_request(message, cp, websocket_info)
                    else:
                        tpaa_request = create_tpaa_associate_response(
                            65000, cp, ServiceStatusKind.instanceNotAvailable.name
                        )
                        # request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
                        is_ber = False
                        if protocol:
                            if "iec61850-tpaa-ber-v1" in protocol:
                                websocket_info.is_ber_protocol = True

                        request = await asyncio.to_thread(encode_tpaa_message, tpaa_request, is_ber)
                        await websocket.send(request)
                        if self.send_msg_callback is not None:
                            self.send_msg_callback(request, datetime.datetime.now())
                        logger.info("Connection failed: Access Point not available")
                        await websocket.close()

            except websockets.exceptions.ConnectionClosedError as e:
                if "no close frame" in str(e):
                    logger.info("Connection aborted without close frame (likely via transport.abort())")
                else:
                    logger.info(f"Connection closed unexpectedly: code={e.code}, reason={e.reason}")

            except websockets.exceptions.ConnectionClosedOK:
                logger.info("Connection closed gracefully")

            except Exception as e:
                logger.info("Unhandled error in start_active:", e)

            finally:
                logger.info(f"Client disconnected: {websocket.remote_address}")
                await self.on_connection_closed(websocket, cp, True, url, port, protocol)

    def add_iec61850_client(self, client):
        """
        Function used for adding IEC61850 Client to endpoint
        """
        self.client_list.append(client)
        if self.send_msg_callback is not None:
            client.install_send_msg_callback(self.send_msg_callback)
        if self.recv_msg_callback is not None:
            client.install_recv_msg_callback(self.recv_msg_callback)

    def add_iec61850_server(self, server):
        """
        Function used for adding IEC61850 Server to endpoint
        """
        self.server_list.append(server)
        if self.send_msg_callback is not None:
            server.install_send_msg_callback(self.send_msg_callback)
        if self.recv_msg_callback is not None:
            server.install_recv_msg_callback(self.recv_msg_callback)

    def get_websocket_info(self, iec61850_client):
        """
        Function used for finding the correct webSocketInfo instance
        """
        websocket_info = next(
            (
                ws_info
                for ws_info in self.websocket_info_list
                if ws_info.websocket.request.path.lstrip("/") == iec61850_client.cp
            ),
            None,
        )
        return websocket_info

    def get_websocket_info_iec61850_server(self, server):
        """
        Function used for finding the correct webSocketInfo instance
        """
        websocket_info = next(
            (
                ws_info
                for ws_info in self.websocket_info_list
                if ws_info.websocket.request.path.lstrip("/") == server.cp
            ),
            None,
        )
        return websocket_info
