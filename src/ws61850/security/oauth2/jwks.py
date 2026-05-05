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

import logging
import ssl

import requests
from jwt import algorithms

logger = logging.getLogger(__name__)


class JwksCache:
    """
    Fetches and caches JWKS keys by kid.

    Responsibilities (only these):
      - fetch JWKS from jwks_uri
      - cache signing keys by kid
      - refresh on cache miss (key rotation)
    """

    def __init__(self, jwks_uri: str, cafile: str | None = None):
        self._jwks_uri = jwks_uri
        self._cafile = cafile
        self._keys: dict = {}

    def _fetch(self) -> None:
        logger.debug("Fetching JWKS from %s", self._jwks_uri)
        session = requests.Session()
        session.verify = self._cafile or True
        response = session.get(self._jwks_uri)
        response.raise_for_status()
        data = response.json()
        self._keys = {k["kid"]: k for k in data["keys"]}
        logger.debug("JWKS fetched: %d key(s) cached", len(self._keys))

    def get_signing_key(self, kid: str):
        """Return the signing key for the given kid, fetching if not cached."""
        if kid not in self._keys:
            logger.debug("Cache miss for kid=%r, refreshing JWKS", kid)
            self._fetch()
        jwk = self._keys.get(kid)
        if jwk is None:
            logger.error("No JWKS key found for kid=%r (available: %s)", kid, list(self._keys))
            raise KeyError(f"No JWKS key found for kid={kid!r}")
        return algorithms.RSAAlgorithm.from_jwk(jwk)
