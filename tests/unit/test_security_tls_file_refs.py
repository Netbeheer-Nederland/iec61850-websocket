# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""TLS material given as `file:<name>` references into the certificate directory."""

import datetime
import ipaddress
import ssl

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from ws61850.security.tls import (
    TLSConfig,
    build_tls_context_from_strings,
    resolve_pem,
)

PEM = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"


def _self_signed(name: str) -> tuple[str, str]:
    """A self-signed certificate (also usable as its own CA) and its key, as PEM."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName(name),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    return cert_pem, key_pem


@pytest.fixture
def cert_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TLS_CERT_DIR", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# resolve_pem
# ---------------------------------------------------------------------------


def test_pem_text_and_empty_values_pass_through(cert_dir):
    assert resolve_pem(PEM) == PEM
    assert resolve_pem(None) is None
    assert resolve_pem("") == ""


def test_file_reference_reads_from_cert_dir(cert_dir):
    (cert_dir / "rti-so.pem").write_text(PEM)
    assert resolve_pem("file:rti-so.pem") == PEM


def test_file_reference_in_subdirectory(cert_dir):
    (cert_dir / "so").mkdir()
    (cert_dir / "so" / "rti-so.pem").write_text(PEM)
    assert resolve_pem("file:so/rti-so.pem") == PEM


def test_explicit_cert_dir_overrides_environment(cert_dir, tmp_path_factory):
    other = tmp_path_factory.mktemp("other")
    (other / "ca.pem").write_text(PEM)
    assert resolve_pem("file:ca.pem", cert_dir=str(other)) == PEM


@pytest.mark.parametrize(
    "name", ["../secret.pem", "/etc/passwd", "so/../../secret.pem"]
)
def test_reference_outside_cert_dir_is_rejected(cert_dir, name):
    (cert_dir.parent / "secret.pem").write_text(PEM)
    with pytest.raises(ValueError, match="outside"):
        resolve_pem(f"file:{name}")


def test_missing_file_names_the_reference(cert_dir):
    with pytest.raises(FileNotFoundError, match="file:absent.pem"):
        resolve_pem("file:absent.pem")


def test_empty_reference_is_rejected(cert_dir):
    with pytest.raises(ValueError, match="no file name"):
        resolve_pem("file:")


# ---------------------------------------------------------------------------
# build_tls_context_from_strings with references
# ---------------------------------------------------------------------------


def test_server_and_client_contexts_from_file_references(cert_dir):
    cert_pem, key_pem = _self_signed("rti-so")
    (cert_dir / "rti-so.pem").write_text(cert_pem)
    (cert_dir / "rti-so-key.pem").write_text(key_pem)
    (cert_dir / "ca.pem").write_text(cert_pem)

    server = build_tls_context_from_strings(
        TLSConfig(
            mode="server", certfile="file:rti-so.pem", keyfile="file:rti-so-key.pem"
        )
    )
    client = build_tls_context_from_strings(
        TLSConfig(mode="client", cafile="file:ca.pem")
    )
    assert isinstance(server, ssl.SSLContext)
    assert isinstance(client, ssl.SSLContext)
    assert client.verify_mode == ssl.CERT_REQUIRED


def test_references_and_pem_text_can_be_mixed(cert_dir):
    cert_pem, key_pem = _self_signed("rti-so")
    (cert_dir / "rti-so-key.pem").write_text(key_pem)
    ctx = build_tls_context_from_strings(
        TLSConfig(mode="server", certfile=cert_pem, keyfile="file:rti-so-key.pem")
    )
    assert isinstance(ctx, ssl.SSLContext)


def test_config_keeps_the_reference(cert_dir):
    """The reference, not the file's content, is what callers see and compare."""
    cert_pem, key_pem = _self_signed("rti-so")
    (cert_dir / "rti-so.pem").write_text(cert_pem)
    (cert_dir / "rti-so-key.pem").write_text(key_pem)
    cfg = TLSConfig(
        mode="server", certfile="file:rti-so.pem", keyfile="file:rti-so-key.pem"
    )
    build_tls_context_from_strings(cfg)
    assert cfg.certfile == "file:rti-so.pem"
    assert cfg.keyfile == "file:rti-so-key.pem"
