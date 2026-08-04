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

import ssl
from dataclasses import dataclass, field
from typing import Literal
import tempfile
import os


@dataclass(frozen=True)
class TLSConfig:
    """Immutable TLS configuration. Pass to build_tls_context() to get an ssl.SSLContext."""
    mode: Literal["client", "server"]
    certfile: str | None = None
    keyfile: str | None = None
    cafile: str | None = None
    verify_peer: bool = True
    check_hostname: bool = True
    min_version: ssl.TLSVersion | None = ssl.TLSVersion.TLSv1_2
    max_version: ssl.TLSVersion | None = None
    ciphers: str | None = None
    require_client_cert: bool = False
    alpn_protocols: tuple[str, ...] = field(default_factory=tuple)
    keylog_file: str | None = None

import tempfile
import ssl
import os

def build_tls_context_from_strings(tls_config: TLSConfig) -> ssl.SSLContext:
    """Build SSLContext from string contents."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if tls_config.mode == "server" else ssl.PROTOCOL_TLS_CLIENT)
    try:
        # Create temp files for cert and key
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as cert_f:
            cert_f.write(tls_config.certfile)
            cert_path = cert_f.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as key_f:
            key_f.write(tls_config.keyfile)
            key_path = key_f.name

        if tls_config.mode == "server":
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            if tls_config.certfile:
                ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
            if tls_config.cafile:
                ctx.load_verify_locations(tls_config.cafile)
            if tls_config.require_client_cert:
                ctx.verify_mode = ssl.CERT_REQUIRED

            if tls_config.min_version is not None:
                ctx.minimum_version = tls_config.min_version
            if tls_config.max_version is not None:
                ctx.maximum_version = tls_config.max_version
            if tls_config.ciphers:
                ctx.set_ciphers(tls_config.ciphers)
            if tls_config.alpn_protocols:
                ctx.set_alpn_protocols(list(tls_config.alpn_protocols))
            if tls_config.keylog_file:
                ctx.keylog_filename = tls_config.keylog_file

            return ctx
    except Exception  as e:
        print("error in build_tls_context_from_strings:", e)
        raise RuntimeError(f"Failed to build TLS context: {e}")

    finally:
        # Always clean up cert and key files
        os.unlink(cert_path)
        os.unlink(key_path)


def build_tls_context(config: TLSConfig) -> ssl.SSLContext:
    """Build an ssl.SSLContext from a TLSConfig."""
    if config.mode == "server":
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        if config.certfile:
            ctx.load_cert_chain(certfile=config.certfile, keyfile=config.keyfile)
        if config.cafile:
            ctx.load_verify_locations(config.cafile)
        if config.require_client_cert:
            ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=config.cafile)
        if config.certfile:
            ctx.load_cert_chain(certfile=config.certfile, keyfile=config.keyfile)
        if not config.verify_peer:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        elif not config.check_hostname:
            ctx.check_hostname = False

    if config.min_version is not None:
        ctx.minimum_version = config.min_version
    if config.max_version is not None:
        ctx.maximum_version = config.max_version
    if config.ciphers:
        ctx.set_ciphers(config.ciphers)
    if config.alpn_protocols:
        ctx.set_alpn_protocols(list(config.alpn_protocols))
    if config.keylog_file:
        ctx.keylog_filename = config.keylog_file

    return ctx
