# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""GET /api/certs and bff.cert_store: listing the certificate volume."""

from __future__ import annotations

import datetime
import ipaddress
import json
import os
import tempfile
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

_tmp_connections_file = Path(tempfile.mkdtemp()) / "connections.json"
_tmp_connections_file.write_text("[]", encoding="utf-8")
os.environ.setdefault("BFF_CONNECTIONS_FILE", str(_tmp_connections_file))

from bff import bff_server, cert_store  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

pytestmark = pytest.mark.unit


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _key_pem(key) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )


def _cert(subject_cn, issuer_cn, key, signing_key, *, ca=False, sans=()):
    now = datetime.datetime.now(datetime.UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject_cn)]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)]))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), True)
    )
    if sans:
        builder = builder.add_extension(x509.SubjectAlternativeName(list(sans)), False)
    return builder.sign(signing_key, hashes.SHA256()).public_bytes(
        serialization.Encoding.PEM
    )


@pytest.fixture
def certs(tmp_path):
    """A certificate directory as rti-cert-generator lays it out, plus extras."""
    ca_key, so_key = _key(), _key()
    (tmp_path / "ca.pem").write_bytes(
        _cert("RTI demo CA", "RTI demo CA", ca_key, ca_key, ca=True)
    )
    (tmp_path / "rti-so.pem").write_bytes(
        _cert(
            "rti-so",
            "RTI demo CA",
            so_key,
            ca_key,
            sans=[
                x509.DNSName("rti-so"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            ],
        )
    )
    so_key_pem = _key_pem(so_key)
    (tmp_path / "rti-so-key.pem").write_bytes(so_key_pem)
    (tmp_path / "pi1").mkdir()
    (tmp_path / "pi1" / "ca.pem").write_bytes((tmp_path / "ca.pem").read_bytes())
    (tmp_path / "notes.txt").write_text("not a certificate")
    (tmp_path / ".hidden.pem").write_bytes(so_key_pem)
    (tmp_path / "broken.pem").write_text("-----BEGIN CERTIFICATE-----\nnope\n")
    return tmp_path, so_key_pem


def test_lists_certificates_and_keys(certs):
    directory, _ = certs
    listing = cert_store.list_certificates(directory)
    by_name = {f["name"]: f for f in listing["files"]}

    assert listing["available"] is True
    assert list(by_name) == [
        "broken.pem",
        "ca.pem",
        "pi1/ca.pem",
        "rti-so-key.pem",
        "rti-so.pem",
    ]

    ca = by_name["ca.pem"]
    assert ca["kind"] == "certificate" and ca["is_ca"] is True
    assert ca["reference"] == "file:ca.pem"

    so = by_name["rti-so.pem"]
    assert so["subject"] == "rti-so" and so["issuer"] == "RTI demo CA"
    assert so["is_ca"] is False
    assert so["sans"] == ["rti-so", "127.0.0.1"]
    assert datetime.datetime.fromisoformat(so["not_after"]) > datetime.datetime.now(
        datetime.UTC
    )

    assert by_name["rti-so-key.pem"] == {
        "name": "rti-so-key.pem",
        "reference": "file:rti-so-key.pem",
        "kind": "private_key",
    }
    assert by_name["pi1/ca.pem"]["reference"] == "file:pi1/ca.pem"
    assert by_name["broken.pem"]["kind"] == "unreadable"


def test_never_returns_key_material(certs):
    directory, key_pem = certs
    dumped = json.dumps(cert_store.list_certificates(directory))
    body = b"".join(key_pem.splitlines()[1:-1]).decode()
    assert "PRIVATE KEY" not in dumped
    assert body[:40] not in dumped


def test_missing_directory_is_reported_not_an_error(tmp_path):
    listing = cert_store.list_certificates(tmp_path / "absent")
    assert listing == {
        "cert_dir": str(tmp_path / "absent"),
        "available": False,
        "files": [],
    }


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads files regardless of mode")
def test_unreadable_file(certs):
    directory, _ = certs
    locked = directory / "locked-key.pem"
    locked.write_text("-----BEGIN PRIVATE KEY-----\n")
    locked.chmod(0)
    try:
        entry = next(
            f
            for f in cert_store.list_certificates(directory)["files"]
            if f["name"] == "locked-key.pem"
        )
        assert entry["kind"] == "unreadable"
    finally:
        locked.chmod(0o600)


def test_endpoint_uses_tls_cert_dir(certs, monkeypatch):
    directory, _ = certs
    monkeypatch.setenv("TLS_CERT_DIR", str(directory))
    body = TestClient(bff_server.app).get("/api/certs").json()
    assert body["ok"] is True
    assert body["cert_dir"] == str(directory)
    assert "file:rti-so.pem" in [f["reference"] for f in body["files"]]
