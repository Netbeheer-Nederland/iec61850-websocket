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
import asyncio
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


async def run_script(path, interactive=False):
    script = BASE_DIR / path
    if interactive:
        # Inherit stdin/stdout/stderr so input() works in the terminal
        proc = await asyncio.create_subprocess_exec(
            "python", str(script),
            stdin=None,
            stdout=None,
            stderr=None
        )
    else:
        # Capture output silently
        proc = await asyncio.create_subprocess_exec(
            "python", str(script),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        print(f"Output from {script}:\n{stdout.decode()}")
        if stderr:
            print(f"Error from {script}:\n{stderr.decode()}")

    await proc.wait()


async def main():
    await asyncio.gather(
        run_script("ws_client.py"),
        run_script("ws_server.py", True)
    )


asyncio.run(main())
