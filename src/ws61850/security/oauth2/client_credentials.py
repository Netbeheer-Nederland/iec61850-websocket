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
import time

import aiohttp


class ClientCredentialsProvider:
    """
    Fetches and caches access tokens using the OAuth2 client_credentials grant.

    Responsibilities (only these):
      - async HTTP token fetch
      - expiry-aware in-memory cache with configurable refresh skew
      - no JWT validation (that lives in validator.py)
    """

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        cafile: str | None = None,
        refresh_skew_seconds: float = 30.0,
    ):
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._cafile = cafile
        self._refresh_skew = refresh_skew_seconds
        self._cached_token: str | None = None
        self._expiry: float = 0.0

    async def get_access_token(self) -> str:
        if self._cached_token and time.monotonic() < self._expiry - self._refresh_skew:
            return self._cached_token

        ssl_ctx = ssl.create_default_context(cafile=self._cafile) if self._cafile else None
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        body = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self._token_url, headers=headers, data=body, ssl=ssl_ctx) as resp:
                data = await resp.json()

        self._cached_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._expiry = time.monotonic() + expires_in
        return self._cached_token
