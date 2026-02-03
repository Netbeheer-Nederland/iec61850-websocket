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
