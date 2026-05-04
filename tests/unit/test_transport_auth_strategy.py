# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
import pytest
from unittest.mock import MagicMock

from ws61850.transport.auth_strategy import AuthContext, AuthStrategy, BearerTokenStrategy, NoAuthStrategy


def test_auth_context_defaults():
    ctx = AuthContext()
    assert ctx.client_id is None
    assert ctx.token_expiry is None


def test_auth_context_fields():
    ctx = AuthContext(client_id="client1", token_expiry=9999.0)
    assert ctx.client_id == "client1"
    assert ctx.token_expiry == 9999.0


def test_no_auth_satisfies_protocol():
    assert isinstance(NoAuthStrategy(), AuthStrategy)


def test_bearer_token_satisfies_protocol():
    assert isinstance(BearerTokenStrategy("tok"), AuthStrategy)


@pytest.mark.asyncio
async def test_no_auth_client_headers_empty():
    headers = await NoAuthStrategy().client_headers()
    assert headers == {}


@pytest.mark.asyncio
async def test_no_auth_server_connection_returns_context():
    ctx = await NoAuthStrategy().authenticate_server_connection(None)
    assert isinstance(ctx, AuthContext)


@pytest.mark.asyncio
async def test_bearer_client_headers():
    headers = await BearerTokenStrategy("mytoken").client_headers()
    assert headers == {"Authorization": "Bearer mytoken"}


@pytest.mark.asyncio
async def test_bearer_server_valid_header():
    request = MagicMock()
    request.headers = {"Authorization": "Bearer validtoken"}
    ctx = await BearerTokenStrategy("validtoken").authenticate_server_connection(request)
    assert isinstance(ctx, AuthContext)


@pytest.mark.asyncio
async def test_bearer_server_missing_header_raises():
    request = MagicMock()
    request.headers = {}
    with pytest.raises(PermissionError):
        await BearerTokenStrategy("t").authenticate_server_connection(request)


@pytest.mark.asyncio
async def test_bearer_server_malformed_header_raises():
    request = MagicMock()
    request.headers = {"Authorization": "Basic abc"}
    with pytest.raises(PermissionError):
        await BearerTokenStrategy("t").authenticate_server_connection(request)
