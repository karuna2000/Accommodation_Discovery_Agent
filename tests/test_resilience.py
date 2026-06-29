import asyncio

import pytest

from src.infrastructure.resilience.bulkhead import Bulkhead
from src.infrastructure.resilience.circuit_breaker import CircuitBreaker, CircuitState
from src.infrastructure.resilience.retry import retry_with_backoff
from src.infrastructure.resilience.timeout import with_timeout
from src.common.errors import CircuitBreakerOpenError, ServiceTimeoutError


class TestCircuitBreaker:
    async def test_starts_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED

    async def test_opens_after_failures(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=60)

        async def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            await cb.call(fail)
        assert cb.state == CircuitState.CLOSED

        with pytest.raises(ValueError):
            await cb.call(fail)
        assert cb.state == CircuitState.OPEN

    async def test_open_rejects_fast(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=60)

        async def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            await cb.call(fail)

        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(fail)

    async def test_closes_after_success(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.01)

        async def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            await cb.call(fail)
        assert cb.state == CircuitState.OPEN

        await asyncio.sleep(0.02)

        async def succeed():
            return "ok"

        result = await cb.call(succeed)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED


class TestRetry:
    async def test_succeeds_on_first_try(self):
        async def ok():
            return "done"

        result = await retry_with_backoff(ok)
        assert result == "done"

    async def test_retries_on_failure(self):
        call_count = 0

        async def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("timeout")
            return "done"

        result = await retry_with_backoff(fail_twice, max_retries=3, base_delay=0.01)
        assert result == "done"
        assert call_count == 3

    async def test_gives_up_after_max_retries(self):
        async def always_fail():
            raise ConnectionError("down")

        with pytest.raises(ConnectionError):
            await retry_with_backoff(always_fail, max_retries=1, base_delay=0.01)


class TestTimeout:
    async def test_raises_on_timeout(self):
        async def slow():
            await asyncio.sleep(10)

        with pytest.raises(ServiceTimeoutError):
            await with_timeout(slow, timeout=0.01)

    async def test_passes_through_result(self):
        async def fast():
            return 42

        result = await with_timeout(fast, timeout=10)
        assert result == 42


class TestBulkhead:
    async def test_executes_function(self):
        h = Bulkhead("test", max_concurrent=2)

        async def work():
            return "done"

        result = await h.execute(work)
        assert result == "done"

    async def test_limits_concurrency(self):
        h = Bulkhead("test", max_concurrent=1)

        in_progress = False
        saw_concurrent = False

        async def slow():
            nonlocal in_progress, saw_concurrent
            in_progress = True
            await asyncio.sleep(0.05)
            in_progress = False

        async def check_concurrent():
            nonlocal saw_concurrent
            if in_progress:
                saw_concurrent = True

        t1 = asyncio.create_task(h.execute(slow))
        await asyncio.sleep(0.01)
        t2 = asyncio.create_task(h.execute(check_concurrent))
        await asyncio.gather(t1, t2)

        assert not saw_concurrent
