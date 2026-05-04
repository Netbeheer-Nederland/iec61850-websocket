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

import time
import uuid

import jwt


class PrivateKeyJWTSigner:
    """
    Builds RFC 7523 client assertion JWTs signed with a private key.

    Used as the client authentication method when calling a token endpoint
    with client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer.
    """

    def __init__(self, client_id: str, private_key, algorithm: str = "RS256", lifetime_seconds: int = 300):
        self._client_id = client_id
        self._private_key = private_key
        self._algorithm = algorithm
        self._lifetime = lifetime_seconds

    def build_assertion(self, token_url: str) -> str:
        now = int(time.time())
        claims = {
            "iss": self._client_id,
            "sub": self._client_id,
            "aud": token_url,
            "jti": str(uuid.uuid4()),
            "iat": now,
            "exp": now + self._lifetime,
        }
        return jwt.encode(claims, self._private_key, algorithm=self._algorithm)


class PrivateKeyJWTProvider:
    """
    TokenProvider that uses private_key_jwt client authentication (RFC 7523).

    Request body sent to the token endpoint:
        grant_type=client_credentials
        client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
        client_assertion=<signed JWT>
        scope=<optional>
    """

    CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"

    def __init__(
        self,
        token_url: str,
        signer: PrivateKeyJWTSigner,
        scope: str | None = None,
        cafile: str | None = None,
    ):
        import ssl
        import aiohttp as _aiohttp
        self._aiohttp = _aiohttp
        self._token_url = token_url
        self._signer = signer
        self._scope = scope
        self._ssl_ctx = ssl.create_default_context(cafile=cafile) if cafile else None
        self._cached_token: str | None = None
        self._expiry: float = 0.0

    async def get_access_token(self) -> str:
        import time
        if self._cached_token and time.monotonic() < self._expiry - 30:
            return self._cached_token

        assertion = self._signer.build_assertion(self._token_url)
        body = {
            "grant_type": "client_credentials",
            "client_assertion_type": self.CLIENT_ASSERTION_TYPE,
            "client_assertion": assertion,
        }
        if self._scope:
            body["scope"] = self._scope

        async with self._aiohttp.ClientSession() as session:
            async with session.post(self._token_url, data=body, ssl=self._ssl_ctx) as resp:
                data = await resp.json()

        self._cached_token = data["access_token"]
        self._expiry = time.monotonic() + data.get("expires_in", 3600)
        return self._cached_token
