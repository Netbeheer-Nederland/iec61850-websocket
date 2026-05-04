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

"""
Deprecated: import from ws61850.security.oauth2.* instead.

This module remains as a backward-compatible shim so that existing callers
(examples/*/connection/runtime.py, endpoint.py) keep working without changes.
"""

import base64
import json

import jwt
import requests
from jwt import ExpiredSignatureError, InvalidTokenError, algorithms, decode

from ws61850.security.oauth2.client_credentials import ClientCredentialsProvider


async def get_access_token(url, client_id, client_secret, cafile):
    provider = ClientCredentialsProvider(
        token_url=url,
        client_id=client_id,
        client_secret=client_secret,
        cafile=cafile,
    )
    return await provider.get_access_token()


def get_jwt_algorithm(token):
    header_b64 = token.split(".")[0]
    padding = "=" * (-len(header_b64) % 4)
    header_b64 += padding
    header_json = base64.urlsafe_b64decode(header_b64).decode("utf-8")
    header = json.loads(header_json)
    return header.get("alg", "No 'alg' found")


def check_token_validity_and_expiry(token, kc_cert, cert, cert_endpoint, token_issuer):
    session = requests.Session()
    session.verify = kc_cert
    response = session.get(cert_endpoint)
    jwks_data = response.json()
    header = jwt.get_unverified_header(token)
    kid = header["kid"]
    jwk = next(key for key in jwks_data["keys"] if key["kid"] == kid)
    signing_key = algorithms.RSAAlgorithm.from_jwk(jwk)

    try:
        decoded = decode(
            token,
            signing_key,
            algorithms=[get_jwt_algorithm(token)],
            audience="account",
            issuer=token_issuer,
        )
        return True, decoded["exp"]
    except ExpiredSignatureError:
        print("Token has expired")
        return False, None
    except InvalidTokenError as e:
        print("Invalid token:", e)
        return False, None


def introspect_token(id, secret, url, access_token, kc_cert, certs):
    if access_token != "":
        data = {"token": access_token, "client_id": id, "client_secret": secret}
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(url, headers=headers, data=data, verify=kc_cert, cert=certs)
        token_response = response.json()
        return token_response.get("active")
    return None
