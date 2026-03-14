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
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_credentials(full_path: Path) -> list[dict[str, Any]]:
    try:
        with full_path.open(encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            logger.error("Credentials file %s does not contain a JSON list.", full_path)
            return []
        return data
    except FileNotFoundError:
        logger.error("Credentials file not found at %s.", full_path)
    except json.JSONDecodeError:
        logger.error("Credentials file is invalid JSON at %s.", full_path)
    except OSError as error:
        logger.error("Failed reading credentials file %s: %s", full_path, error)
    return []


def save_credentials(full_path: Path, credentials: list[dict[str, Any]]) -> None:
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with full_path.open("w", encoding="utf-8") as file:
            json.dump(credentials, file, indent=4)
    except OSError as error:
        raise OSError(f"Unable to write credentials file {full_path}: {error}") from error
