# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
import time
import pytest
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from ws61850.security.oauth2.private_jwt import PrivateKeyJWTSigner


@pytest.fixture(scope="module")
def rsa_key_pair():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    return private_key, private_key.public_key()


def test_build_assertion_is_valid_jwt(rsa_key_pair):
    private_key, public_key = rsa_key_pair
    signer = PrivateKeyJWTSigner(client_id="my-client", private_key=private_key)
    token = signer.build_assertion("https://auth.example.com/token")
    assert isinstance(token, str)
    # Should decode without error using the matching public key
    decoded = jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        audience="https://auth.example.com/token",
        options={"verify_exp": False},
    )
    assert decoded["iss"] == "my-client"
    assert decoded["sub"] == "my-client"
    assert decoded["aud"] == "https://auth.example.com/token"


def test_build_assertion_contains_jti(rsa_key_pair):
    private_key, _ = rsa_key_pair
    signer = PrivateKeyJWTSigner(client_id="c", private_key=private_key)
    token = signer.build_assertion("https://example.com")
    header = jwt.get_unverified_header(token)
    payload = jwt.decode(token, options={"verify_signature": False})
    assert "jti" in payload


def test_build_assertion_exp_in_future(rsa_key_pair):
    private_key, _ = rsa_key_pair
    signer = PrivateKeyJWTSigner(client_id="c", private_key=private_key, lifetime_seconds=300)
    token = signer.build_assertion("https://example.com")
    payload = jwt.decode(token, options={"verify_signature": False})
    assert payload["exp"] > time.time()


def test_different_tokens_have_unique_jti(rsa_key_pair):
    private_key, _ = rsa_key_pair
    signer = PrivateKeyJWTSigner(client_id="c", private_key=private_key)
    t1 = signer.build_assertion("https://example.com")
    t2 = signer.build_assertion("https://example.com")
    p1 = jwt.decode(t1, options={"verify_signature": False})
    p2 = jwt.decode(t2, options={"verify_signature": False})
    assert p1["jti"] != p2["jti"]
