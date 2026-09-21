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

from ws61850.endpoint.active_endpoint import ActiveEndpoint
from ws61850.endpoint.base import EndpointProtocol, WebSocketInfo
from ws61850.endpoint.passive_endpoint import PassiveEndpoint

__all__ = [
    "WebSocketInfo",
    "EndpointProtocol",
    "PassiveEndpoint",
    "ActiveEndpoint",
    "create_endpoint",
]


def create_endpoint(mode: str, **kwargs) -> PassiveEndpoint | ActiveEndpoint:
    """Factory: create_endpoint('passive', ...) or create_endpoint('active', ...)."""
    if mode == "passive":
        return PassiveEndpoint(**kwargs)
    if mode == "active":
        return ActiveEndpoint(**kwargs)
    raise ValueError(f"Unknown mode: {mode!r}")
