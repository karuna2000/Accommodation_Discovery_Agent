import asyncio


class Bulkhead:
    def __init__(self, name: str, max_concurrent: int = 2):
        self.name = name
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def execute(self, fn, *args, **kwargs):
        async with self._semaphore:
            return await fn(*args, **kwargs)
