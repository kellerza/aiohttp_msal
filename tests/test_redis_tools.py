"""Test redis tools."""
from json import dumps
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, Mock, call

import pytest

from aiohttp_msal.redis_tools import Redis, session_iter


@pytest.fixture
def redis() -> Redis:
    """Get a redis Mock instance."""
    testdata = {
        "a": dumps({"created": 1, "session": {"key": "a", "a": 1, "b": "2a"}}),
        "b": dumps({"created": 2, "session": {"key": "b", "a": 1, "b": "2b"}}),
        "c": dumps({"created": 3, "session": {"key": "c", "a": 5, "b": "6c"}}),
    }

    async def scan_iter(*, count: int, match: str) -> AsyncGenerator[str, None]:
        """Mock keys."""
        assert count == 100
        assert match == "a*"
        for key in testdata:
            yield key

    red = Mock()
    red.scan_iter = MagicMock(side_effect=scan_iter)
    red.get = AsyncMock(side_effect=list(testdata.values()))
    return red


@pytest.mark.asyncio
async def test_session_iter_fail(redis: Redis) -> None:
    """Test session iter."""
    match = {"a": 1}
    with pytest.raises(ValueError):
        async for _ in session_iter(redis, match=match, key_match="a*"):
            pass

    match = {"a": "1"}
    async for _ in session_iter(redis, match=match, key_match="a*"):
        assert False, "no match expected"


@pytest.mark.asyncio
async def test_session_iter(redis: Redis) -> None:
    """Test session iter."""
    match = {"b": "2"}
    expected = ["a", "b"]
    async for key, created, ses in session_iter(redis, match=match, key_match="a*"):
        assert expected.pop(0) == key
        assert key == ses["key"]
        assert created in (1, 2)
        assert key in ("a", "b")

    assert redis.scan_iter.call_args[1]["match"] == "a*"
    assert redis.scan_iter.call_args[1]["count"] == 100
    assert redis.scan_iter.call_args_list == [call(count=100, match="a*")]
