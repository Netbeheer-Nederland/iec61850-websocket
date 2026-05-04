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


class Ws61850Error(Exception):
    """Base error for all ws61850 library errors."""


class TpaaDecodeError(Ws61850Error):
    """Raised when a TPAA message cannot be decoded or has unexpected structure."""


class AssociationError(Ws61850Error):
    """Raised when association establishment or teardown fails."""


class TransportError(Ws61850Error):
    """Raised when a WebSocket transport operation fails."""


class AuthenticationError(Ws61850Error):
    """Raised when OAuth2 or TLS authentication fails."""
