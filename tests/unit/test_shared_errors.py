# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
import pytest

from ws61850.shared.errors import (
    AssociationError,
    AuthenticationError,
    TpaaDecodeError,
    TransportError,
    Ws61850Error,
)


def test_hierarchy():
    assert issubclass(TpaaDecodeError, Ws61850Error)
    assert issubclass(AssociationError, Ws61850Error)
    assert issubclass(TransportError, Ws61850Error)
    assert issubclass(AuthenticationError, Ws61850Error)


def test_base_is_exception():
    assert issubclass(Ws61850Error, Exception)


def test_catch_as_base():
    with pytest.raises(Ws61850Error):
        raise TpaaDecodeError("bad frame")


def test_message_preserved():
    exc = AssociationError("handshake failed")
    assert str(exc) == "handshake failed"
