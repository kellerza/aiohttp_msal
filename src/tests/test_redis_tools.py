"""Test redis tools."""

import asyncio
import json
from collections.abc import AsyncGenerator
from json import dumps
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, call

import pytest
from redis.asyncio import Redis

from aiohttp_msal import redis_tools
from aiohttp_msal.msal_async import AsyncMSAL
from aiohttp_msal.redis_tools import session_iter
from aiohttp_msal.settings import ENV


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
    match1 = {"a": 1}
    with pytest.raises(ValueError):
        async for _ in session_iter(redis, match=match1, key_match="a*"):  # type:ignore[arg-type]
            pass

    match = {"a": "1"}
    async for _ in session_iter(redis, match=match, key_match="a*"):
        raise ValueError("no match expected")


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

    assert redis.scan_iter.call_args[1]["match"] == "a*"  # type:ignore[attr-defined]
    assert redis.scan_iter.call_args[1]["count"] == 100  # type:ignore[attr-defined]
    assert redis.scan_iter.call_args_list == [call(count=100, match="a*")]  # type:ignore[attr-defined]


@pytest.mark.asyncio
async def test_redis_get_and_get_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test redis_get and redis_get_json."""
    key = "k1"
    payload = {"x": 1}

    db = Mock()
    db.get = AsyncMock(return_value=json.dumps(payload))
    monkeypatch.setattr(ENV, "database", db)

    res = await redis_tools.redis_get_json(key)
    assert res == payload

    # redis_get returns str/decoded bytes
    db.get = AsyncMock(return_value="string-value")
    assert await redis_tools.redis_get(key) == "string-value"

    db.get = AsyncMock(return_value=b"byte-value")
    assert await redis_tools.redis_get(key) == "byte-value"


@pytest.mark.asyncio
async def test_redis_scan_keys_and_set_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """scan_iter yields mixed bytes/str."""

    async def scan_iter(**kwargs: Any) -> AsyncGenerator[str | bytes]:
        yield b"one"
        yield "two"

    db = Mock()
    db.scan_iter = scan_iter
    monkeypatch.setattr(ENV, "database", db)

    keys = await redis_tools.redis_scan_keys("*")
    assert keys == ["one", "two"]

    # Test redis_set_set: current members contain 'a' and 'b'
    async_db = Mock()
    async_db.smembers = AsyncMock(return_value={b"a", "b"})
    async_db.srem = AsyncMock()
    async_db.sadd = AsyncMock()
    monkeypatch.setattr(ENV, "database", async_db)

    await redis_tools.redis_set_set("skey", {"b", "c"})

    # 'a' should be removed, 'c' should be added
    async_db.srem.assert_awaited()
    async_db.sadd.assert_awaited()


@pytest.mark.asyncio
async def test_async_msal_factory_save_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prepare ENV.database to capture set calls."""
    async_db = Mock()
    async_db.set = AsyncMock()
    monkeypatch.setattr(ENV, "database", async_db)

    key = "sess:1"
    created = 123
    session = {"mail": "me@example.com", "token_cache": "tok"}

    inst = redis_tools.async_msal_factory(AsyncMSAL, key, created, session)
    assert isinstance(inst, AsyncMSAL)

    # Call the save callback, which schedules an async task to write to redis
    if inst.save_callback:
        inst.save_callback({})

    # Allow scheduled task to run
    await asyncio.sleep(0)

    async_db.set.assert_awaited()
    called_key, called_val = async_db.set.await_args.args  # type: ignore[union-attr]
    assert called_key == key
    assert json.loads(called_val) == {"created": created, "session": session}


@pytest.mark.asyncio
async def test_get_session_returns_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch session_iter to yield one matching session."""

    async def fake_iter(
        redis: Redis, /, *, match: str | None = None, key_match: str | None = None
    ) -> AsyncGenerator[Any]:
        yield "k", 1, {"mail": "u@example.com", "token_cache": ""}

    monkeypatch.setattr(redis_tools, "session_iter", fake_iter)

    inst = await redis_tools.get_session(AsyncMSAL, "u@example.com", redis=Mock())
    assert isinstance(inst, AsyncMSAL)
    assert inst.session.get("mail") == "u@example.com"

    # Not found should raise
    async def empty_iter(
        redis: Redis, /, *, match: str | None = None, key_match: str | None = None
    ) -> AsyncGenerator[Any]:
        if False:
            yield

    monkeypatch.setattr(redis_tools, "session_iter", empty_iter)
    with pytest.raises(ValueError):
        await redis_tools.get_session(AsyncMSAL, "not@here")
