import asyncio
import logging

logger = logging.getLogger(__name__)


async def run_tasks(tasks):
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        # Preserve cancellation semantics
        raise
    except Exception:
        logger.exception("Unexpected exception during task execution.")
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
