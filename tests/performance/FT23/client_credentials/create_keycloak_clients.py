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
import argparse
import asyncio
import logging
from pathlib import Path

from utils.keycloak_client_provisioner import provision_clients

DEFAULT_NUM_CLIENTS_IN_BATCH = 15
CLIENT_START_ID = 1
CREDENTIALS_FILE = "data/client_credentials.json"
logger = logging.getLogger(__name__)


def resolve_credentials_path(credentials_file_path: str) -> Path:
    path = Path(credentials_file_path)
    if path.is_absolute():
        return path
    project_root = Path(__file__).resolve().parents[1]
    return (project_root / path).resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create and authenticate Keycloak clients.")
    parser.add_argument(
        "--num-clients-in-batch",
        type=int,
        default=DEFAULT_NUM_CLIENTS_IN_BATCH,
        help=f"Number of clients to create/authenticate (default: {DEFAULT_NUM_CLIENTS_IN_BATCH}).",
    )
    return parser.parse_args()


async def run_batch(num_clients_in_batch: int):
    client_end_id = CLIENT_START_ID + num_clients_in_batch - 1
    logger.info(
        "--- Starting Client Runner Batch 1 (Clients cp%s to cp%s) ---",
        CLIENT_START_ID,
        client_end_id,
    )

    credentials_path = resolve_credentials_path(CREDENTIALS_FILE)

    logger.info("Provisioning clients in Keycloak and saving credentials...")
    try:
        # Note: If clients already exist from a previous run, this will skip creation
        provision_clients(
            num_clients_to_gen=num_clients_in_batch, start_id=CLIENT_START_ID, credentials_file_path=credentials_path
        )
    except ConnectionError as ex:
        logger.error("CRITICAL ERROR in Step 1 (Client Generation): %s. Cannot proceed.", ex)
        return
    except (OSError, ValueError, RuntimeError) as ex:
        logger.error("Unexpected error during client generation: %s", ex, exc_info=True)
        return

    logger.info("-" * 40)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()
    try:
        asyncio.run(run_batch(args.num_clients_in_batch))
    except KeyboardInterrupt:
        logger.warning("Execution interrupted by user.")
    except (RuntimeError, OSError) as error:
        logger.error("Critical error in main runner: %s", error, exc_info=True)
