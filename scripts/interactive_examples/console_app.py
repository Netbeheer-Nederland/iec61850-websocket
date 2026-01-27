import asyncio
import subprocess

async def run_script(path, interactive=False):
    if interactive:
        # Inherit stdin/stdout/stderr so input() works in the terminal
        proc = await asyncio.create_subprocess_exec(
            "python", path,
            stdin=None,
            stdout=None,
            stderr=None
        )
    else:
        # Capture output silently
        proc = await asyncio.create_subprocess_exec(
            "python", path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        print(f"Output from {path}:\n{stdout.decode()}")
        if stderr:
            print(f"Error from {path}:\n{stderr.decode()}")

    await proc.wait()
async def main():
    await asyncio.gather(
        run_script("ws_client.py"),
        run_script("ws_server.py", True)
    )

asyncio.run(main())