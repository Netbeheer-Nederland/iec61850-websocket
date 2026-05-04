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
"""Flask entrypoint for the IEC 61850 GUI."""

import logging
import os

from bff.backend.app_factory import create_app

logging.basicConfig(
    level=os.environ.get("WS61850_GUI_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Flask app on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=True)
