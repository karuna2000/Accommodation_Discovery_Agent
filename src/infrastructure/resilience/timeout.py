import asyncio

from src.common.errors import ServiceTimeoutError


async def with_timeout(fn, *args, timeout: float, **kwargs):
    try:
        return await asyncio.wait_for(fn(*args, **kwargs), timeout=timeout)
    except asyncio.TimeoutError as exc:
        fn_name = getattr(fn, "__name__", str(fn))
        raise ServiceTimeoutError(fn_name, timeout) from exc
