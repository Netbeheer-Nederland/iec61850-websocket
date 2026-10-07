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

import os
import ssl
import tempfile
from dataclasses import dataclass, field
from typing import Literal


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


FILE_REF_PREFIX = "file:"
DEFAULT_CERT_DIR = "/certs"


def resolve_pem(value: str | None, cert_dir: str | None = None) -> str | None:
    """Return PEM text for a TLS field that is either PEM text or a file reference.

    A value ``file:<name>`` names a file in the certificate directory -
    ``cert_dir``, else the ``TLS_CERT_DIR`` environment variable, else
    ``/certs`` (where the rti-demo's docker-compose.yml mounts testing/certs) - and
    is read when called. Anything else, including ``None``, is returned as is.
    A name that resolves outside the certificate directory is rejected.
    """
    if not value or not value.startswith(FILE_REF_PREFIX):
        return value
    name = value[len(FILE_REF_PREFIX) :].strip()
    if not name:
        raise ValueError(f"TLS file reference {value!r} has no file name")
    base = os.path.realpath(
        cert_dir or os.environ.get("TLS_CERT_DIR") or DEFAULT_CERT_DIR
    )
    path = os.path.realpath(os.path.join(base, name))
    if os.path.commonpath([base, path]) != base:
        raise ValueError(
            f"TLS file reference {value!r} points outside the certificate "
            f"directory {base}"
        )
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(
            f"TLS file reference {value!r}: {path} not found"
        ) from None


def build_tls_context_from_strings(tls_config: TLSConfig) -> ssl.SSLContext:
    """Build SSLContext from string contents.

    certfile, keyfile and cafile hold PEM text or ``file:<name>`` references
    into the certificate directory (see resolve_pem). References are read
    here, each time a context is built; tls_config itself keeps them as given.
    """
    cert_path = key_path = ca_path = None  # ← Initialize first

    try:
        cert_text = resolve_pem(tls_config.certfile)
        key_text = resolve_pem(tls_config.keyfile)
        ca_text = resolve_pem(tls_config.cafile)

        if tls_config.mode == "server":
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".pem", delete=False
            ) as cert_f:
                cert_f.write(cert_text)
                cert_path = cert_f.name

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".pem", delete=False
            ) as key_f:
                key_f.write(key_text)
                key_path = key_f.name

            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)

            if ca_text:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".pem", delete=False
                ) as ca_f:
                    ca_f.write(ca_text)
                    ca_path = ca_f.name
                ctx.load_verify_locations(ca_path)

            if tls_config.require_client_cert:
                ctx.verify_mode = ssl.CERT_REQUIRED

        else:  # Client mode
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".pem", delete=False
            ) as ca_f:
                ca_f.write(ca_text)
                ca_path = ca_f.name
            ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=ca_path)

            if not tls_config.verify_peer:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            elif not tls_config.check_hostname:
                ctx.check_hostname = False

        # Common settings
        if tls_config.min_version:
            ctx.minimum_version = tls_config.min_version
        if tls_config.max_version:
            ctx.maximum_version = tls_config.max_version
        if tls_config.ciphers:
            ctx.set_ciphers(tls_config.ciphers)
        if tls_config.alpn_protocols:
            ctx.set_alpn_protocols(list(tls_config.alpn_protocols))
        if tls_config.keylog_file:
            ctx.keylog_filename = tls_config.keylog_file

        return ctx

    except Exception as e:
        print("error in build_tls_context_from_strings:", e)
        raise RuntimeError(f"Failed to build TLS context: {e}")

    finally:
        # Safe cleanup - only unlink if path exists
        for path in [cert_path, key_path, ca_path]:
            if path is not None:
                try:
                    os.unlink(path)
                except Exception:
                    pass


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
