import asyncio
import subprocess


async def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run a command via subprocess.run in a thread pool executor.

    This works with both ProactorEventLoop and SelectorEventLoop,
    unlike asyncio.create_subprocess_exec which is Proactor-only on Windows.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: subprocess.run(cmd, capture_output=True),
    )
