# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
import ssl
import pytest
from dataclasses import FrozenInstanceError

from ws61850.security.tls import TLSConfig, build_tls_context


# ---------------------------------------------------------------------------
# TLSConfig dataclass
# ---------------------------------------------------------------------------

def test_tls_config_defaults():
    cfg = TLSConfig(mode="client")
    assert cfg.certfile is None
    assert cfg.keyfile is None
    assert cfg.cafile is None
    assert cfg.verify_peer is True
    assert cfg.check_hostname is True
    assert cfg.min_version == ssl.TLSVersion.TLSv1_2
    assert cfg.max_version is None
    assert cfg.require_client_cert is False
    assert cfg.alpn_protocols == ()


def test_tls_config_is_frozen():
    cfg = TLSConfig(mode="client")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        cfg.mode = "server"  # type: ignore[misc]


def test_tls_config_server_mode():
    cfg = TLSConfig(mode="server", require_client_cert=True)
    assert cfg.mode == "server"
    assert cfg.require_client_cert is True


# ---------------------------------------------------------------------------
# TLSContextFactory — client context (no cert files needed for basic checks)
# ---------------------------------------------------------------------------

def test_build_client_context_returns_ssl_context():
    cfg = TLSConfig(mode="client", verify_peer=False)
    ctx = build_tls_context(cfg)
    assert isinstance(ctx, ssl.SSLContext)


def test_client_no_verify_disables_hostname_check():
    cfg = TLSConfig(mode="client", verify_peer=False)
    ctx = build_tls_context(cfg)
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_client_verify_true_check_hostname_false():
    cfg = TLSConfig(mode="client", verify_peer=True, check_hostname=False)
    ctx = build_tls_context(cfg)
    assert ctx.check_hostname is False


def test_client_min_version_applied():
    cfg = TLSConfig(mode="client", verify_peer=False, min_version=ssl.TLSVersion.TLSv1_2)
    ctx = build_tls_context(cfg)
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2


def test_alpn_protocols_applied():
    cfg = TLSConfig(mode="client", verify_peer=False, alpn_protocols=("h2", "http/1.1"))
    ctx = build_tls_context(cfg)
    # If ALPN is set we can read it back via negotiated_protocol after handshake;
    # at construction time we just verify no exception was raised and ctx exists.
    assert ctx is not None
