# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
import json
import time

import jwt
import pytest
import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import algorithms

from ws61850.security.oauth2.validator import JwtValidator

ISSUER = "https://auth.example.com/realms/test"
AUDIENCE = "account"


@pytest.fixture(scope="module")
def private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())


class FakeJwks:
    """JwksCache stand-in: knows one key, raises KeyError for any other kid
    (as JwksCache does after refreshing), or fails like an unreachable JWKS."""

    def __init__(self, kid, public_key, fetch_error=None):
        self._keys = {kid: public_key}
        self._fetch_error = fetch_error

    def get_signing_key(self, kid):
        if self._fetch_error:
            raise self._fetch_error
        if kid not in self._keys:
            raise KeyError(f"No JWKS key found for kid={kid!r}")
        return self._keys[kid]


def make_token(private_key, kid="key-1", **claims):
    payload = {"iss": ISSUER, "aud": AUDIENCE, "sub": "client", "exp": int(time.time()) + 300, **claims}
    headers = {"kid": kid} if kid is not None else {}
    return jwt.encode(payload, private_key, algorithm="RS256", headers=headers)


@pytest.fixture
def validator(private_key):
    public_jwk = json.loads(algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    return JwtValidator(FakeJwks("key-1", algorithms.RSAAlgorithm.from_jwk(public_jwk)), ISSUER, AUDIENCE)


def test_valid_token_is_accepted(validator, private_key):
    is_valid, claims = validator.validate(make_token(private_key))
    assert is_valid is True
    assert claims.subject == "client"


def test_unknown_kid_is_an_invalid_token_not_an_error(validator, private_key):
    # A token signed by a key the issuer doesn't publish is forged or foreign:
    # rejected as invalid (401), not reported as verification unavailable.
    assert validator.validate(make_token(private_key, kid="not-a-known-key")) == (False, None)


def test_missing_kid_is_an_invalid_token(validator, private_key):
    assert validator.validate(make_token(private_key, kid=None)) == (False, None)


def test_wrong_signature_is_an_invalid_token(validator):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    assert validator.validate(make_token(other_key)) == (False, None)


def test_jwks_unreachable_still_raises(private_key):
    # Not the token's fault - the caller reports verification unavailable (503).
    validator = JwtValidator(
        FakeJwks("key-1", None, fetch_error=requests.ConnectionError("JWKS down")), ISSUER, AUDIENCE
    )
    with pytest.raises(requests.ConnectionError):
        validator.validate(make_token(private_key))


def test_wrong_issuer_logs_expected_and_received(validator, private_key, caplog):
    token = make_token(private_key, iss="https://localhost:8443/realms/test")
    with caplog.at_level("WARNING", logger="ws61850.security.oauth2.validator"):
        assert validator.validate(token) == (False, None)
    assert f"expected {ISSUER!r}" in caplog.text
    assert "got 'https://localhost:8443/realms/test'" in caplog.text
