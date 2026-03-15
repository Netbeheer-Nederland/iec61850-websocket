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


class TLSConfiguration:
    def __init__(self, cert_path, key_path, is_ws_server):
        self.key_path = key_path
        self.cert_path = cert_path
        self.ssl_context = None
        self.is_ws_server = is_ws_server

        if is_ws_server:
            self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self.ssl_context.load_cert_chain(certfile=cert_path, keyfile=key_path)
        else:
            self.ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            self.ssl_context.load_verify_locations(cert_path)

    def set_min_and_max_version(self, min_version=None, max_version=None):
        # setting TLS version
        if min_version is not None:
            self.ssl_context.minimum_version = min_version
        if max_version is not None:
            self.ssl_context.maximum_version = max_version