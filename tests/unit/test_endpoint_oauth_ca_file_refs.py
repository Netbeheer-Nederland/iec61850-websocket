# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The OAuth auth server CA given as a `file:<name>` reference into the certificate directory."""

import pytest

import ws61850.endpoint.active_endpoint as active_endpoint
from ws61850.endpoint.active_endpoint import ActiveEndpoint
from ws61850.endpoint.passive_endpoint import PassiveEndpoint

CA_PEM = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"


@pytest.fixture
def cert_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TLS_CERT_DIR", str(tmp_path))
    (tmp_path / "ca.pem").write_text(CA_PEM)
    return tmp_path


class TestPassiveEndpoint:
    async def test_reads_the_referenced_ca_into_its_cafile(self, cert_dir):
        endpoint = PassiveEndpoint()

        await endpoint.reconfigure_oauth(False, kc_cert="file:ca.pem")

        with open(endpoint._kc_cert, encoding="utf-8") as f:
            assert f.read() == CA_PEM

    async def test_still_takes_pem_text(self, cert_dir):
        endpoint = PassiveEndpoint()

        await endpoint.reconfigure_oauth(False, kc_cert=CA_PEM)

        with open(endpoint._kc_cert, encoding="utf-8") as f:
            assert f.read() == CA_PEM

    async def test_missing_file_leaves_the_oauth_setup_as_it_was(self, cert_dir):
        endpoint = PassiveEndpoint()

        with pytest.raises(FileNotFoundError):
            await endpoint.reconfigure_oauth(
                True,
                certificate_endpoint="https://idp/certs",
                token_issuer="https://idp",
                kc_cert="file:missing.pem",
            )

        assert endpoint._oauth_enable is False
        assert endpoint._cert_endpoint is None
        assert endpoint._jwt_validator is None


class TestActiveEndpoint:
    async def test_fetches_its_token_with_the_referenced_ca(
        self, cert_dir, monkeypatch
    ):
        seen = {}

        class FakeProvider:
            def __init__(self, *, token_url, client_id, client_secret, cafile):
                with open(cafile, encoding="utf-8") as f:
                    seen["ca"] = f.read()

            async def get_access_token(self):
                return "token"

        async def fake_start(*args, **kwargs):
            return None

        monkeypatch.setattr(active_endpoint, "ClientCredentialsProvider", FakeProvider)
        endpoint = ActiveEndpoint()
        monkeypatch.setattr(endpoint, "start", fake_start)

        await endpoint.reconfigure_oauth(
            "so",
            8765,
            "cp1",
            True,
            token_endpoint="https://idp/token",
            client_id="rti-fsp",
            client_secret="secret",
            kc_cert="file:ca.pem",
        )
        await endpoint._connect_task

        assert seen["ca"] == CA_PEM
        assert endpoint._assoc_handler._kc_cert == CA_PEM

    async def test_missing_file_leaves_the_oauth_setup_as_it_was(self, cert_dir):
        endpoint = ActiveEndpoint()

        with pytest.raises(FileNotFoundError):
            await endpoint.reconfigure_oauth(
                "so",
                8765,
                "cp1",
                True,
                token_endpoint="https://idp/token",
                client_id="rti-fsp",
                kc_cert="file:missing.pem",
            )

        assert endpoint._oauth_enable is False
        assert endpoint._assoc_handler._kc_cert is None
