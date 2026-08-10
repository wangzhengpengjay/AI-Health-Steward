"""Unit tests for security helpers (P0-3 / P1-3): auth + rate limiting."""
import asyncio

from app.core.security import _SlidingWindowLimiter, _extract_member_id


class TestExtractMemberId:
    def test_chat_path(self) -> None:
        assert _extract_member_id("/api/v1/members/42/chat") == 42

    def test_stream_path(self) -> None:
        assert _extract_member_id("/api/v1/members/3/chat/stream") == 3

    def test_collection_path_returns_none(self) -> None:
        assert _extract_member_id("/api/v1/members") is None

    def test_no_digits_returns_none(self) -> None:
        assert _extract_member_id("/api/v1/health") is None


class TestSlidingWindowLimiter:
    def test_allows_up_to_limit_then_blocks(self) -> None:
        limiter = _SlidingWindowLimiter(max_requests=3, window_seconds=60)

        async def run() -> None:
            for _ in range(3):
                assert await limiter.acquire("k") is True
            assert await limiter.acquire("k") is False

        asyncio.run(run())

    def test_independent_keys(self) -> None:
        limiter = _SlidingWindowLimiter(max_requests=1, window_seconds=60)

        async def run() -> None:
            assert await limiter.acquire("a") is True
            assert await limiter.acquire("b") is True
            assert await limiter.acquire("a") is False

        asyncio.run(run())

    def test_window_expiry_allows_again(self) -> None:
        limiter = _SlidingWindowLimiter(max_requests=1, window_seconds=1)

        async def run() -> None:
            assert await limiter.acquire("k") is True
            assert await limiter.acquire("k") is False
            import time
            time.sleep(1.05)
            assert await limiter.acquire("k") is True

        asyncio.run(run())

    def test_reset_clears_counts(self) -> None:
        limiter = _SlidingWindowLimiter(max_requests=1, window_seconds=60)

        async def run() -> None:
            assert await limiter.acquire("k") is True
            assert await limiter.acquire("k") is False
            limiter.reset("k")
            assert await limiter.acquire("k") is True

        asyncio.run(run())