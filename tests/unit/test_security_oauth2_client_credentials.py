# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ws61850.security.oauth2.client_credentials import ClientCredentialsProvider


def _make_provider(**kwargs):
    return ClientCredentialsProvider(
        token_url="https://auth.example.com/token",
        client_id="my-client",
        client_secret="secret",
        **kwargs,
    )


def _mock_token_response(token="access-token", expires_in=3600):
    resp = AsyncMock()
    resp.json = AsyncMock(return_value={"access_token": token, "expires_in": expires_in})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _mock_session(resp):
    session = MagicMock()
    session.post = MagicMock(return_value=resp)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.mark.asyncio
async def test_fetches_token_on_first_call():
    provider = _make_provider()
    resp = _mock_token_response("tok1")
    session = _mock_session(resp)

    with patch("aiohttp.ClientSession", return_value=session):
        token = await provider.get_access_token()

    assert token == "tok1"


@pytest.mark.asyncio
async def test_caches_token_on_second_call():
    provider = _make_provider()
    resp = _mock_token_response("tok-cached", expires_in=3600)
    session = _mock_session(resp)

    with patch("aiohttp.ClientSession", return_value=session):
        t1 = await provider.get_access_token()
        t2 = await provider.get_access_token()

    assert t1 == t2 == "tok-cached"
    # Only one HTTP call should have been made
    assert session.post.call_count == 1


@pytest.mark.asyncio
async def test_refreshes_when_expiry_close():
    provider = _make_provider(refresh_skew_seconds=30.0)
    # Manually set cache state with token almost expired
    provider._cached_token = "old-token"
    provider._expiry = time.monotonic() + 10  # less than skew of 30s

    resp = _mock_token_response("new-token")
    session = _mock_session(resp)

    with patch("aiohttp.ClientSession", return_value=session):
        token = await provider.get_access_token()

    assert token == "new-token"


@pytest.mark.asyncio
async def test_default_expires_in_fallback():
    provider = _make_provider()
    resp = AsyncMock()
    resp.json = AsyncMock(return_value={"access_token": "tok"})  # no expires_in
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session = _mock_session(resp)

    with patch("aiohttp.ClientSession", return_value=session):
        token = await provider.get_access_token()

    assert token == "tok"
    assert provider._expiry > time.monotonic()
