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
from dataclasses import dataclass

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from ws61850.security.oauth2.jwks import JwksCache

logger = logging.getLogger(__name__)


@dataclass
class TokenClaims:
    expiry: int
    subject: str | None = None
    audience: str | None = None


class JwtValidator:
    """
    Validates bearer tokens via JWKS signature verification.

    Responsibilities (only these):
      - issuer / audience / expiry / not-before checks
      - signature via JWKS (delegates key fetch to JwksCache)
      - clock skew tolerance
      - no token acquisition (that lives in client_credentials / private_jwt)
    """

    def __init__(
        self,
        jwks_cache: JwksCache,
        issuer: str,
        audience: str,
        leeway_seconds: int = 10,
    ):
        self._jwks = jwks_cache
        self._issuer = issuer
        self._audience = audience
        self._leeway = leeway_seconds

    def validate(self, token: str) -> tuple[bool, TokenClaims | None]:
        """
        Returns (is_valid, claims_or_None).
        Returns (False, None) on expiry or invalid signature rather than raising,
        matching the original oauth.py contract.
        """
        try:
            header = jwt.get_unverified_header(token)
            kid = header["kid"]
            alg = header.get("alg", "RS256")
            signing_key = self._jwks.get_signing_key(kid)

            decoded = jwt.decode(
                token,
                signing_key,
                algorithms=[alg],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
            )
            claims = TokenClaims(
                expiry=decoded["exp"],
                subject=decoded.get("sub"),
                audience=decoded.get("aud"),
            )
            logger.debug("Token valid kid=%r alg=%r sub=%r exp=%s", kid, alg, claims.subject, claims.expiry)
            return True, claims

        except ExpiredSignatureError:
            logger.warning("Token expired (kid=%r)", jwt.get_unverified_header(token).get("kid"))
            return False, None
        except InvalidTokenError as e:
            logger.warning("Token invalid: %s", e)
            return False, None
