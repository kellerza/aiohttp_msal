"""Redis tools for sessions."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from redis.asyncio import Redis, from_url

from aiohttp_msal.msal_async import AsyncMSAL
from aiohttp_msal.settings import ENV as MENV

_LOGGER = logging.getLogger(__name__)

SES_KEYS = ("mail", "name", "m_mail", "m_name")


@asynccontextmanager
async def get_redis() -> AsyncGenerator[Redis, None]:
    """Get a Redis connection."""
    if MENV.database:
        _LOGGER.debug("Using redis from environment")
        yield MENV.database
        return
    _LOGGER.info("Connect to Redis %s", MENV.REDIS)
    redis = from_url(MENV.REDIS)  # decode_responses=True not allowed aiohttp_session
    MENV.database = redis
    try:
        yield redis
    finally:
        MENV.database = None  # type:ignore[assignment]
        await redis.close()


async def session_iter(
    redis: Redis,
    *,
    match: dict[str, str] | None = None,
    key_match: str | None = None,
) -> AsyncGenerator[tuple[str, int, dict[str, Any]], None]:
    """Iterate over the Redis keys to find a specific session.

    match: Filter based on session content (i.e. mail/name)
    key_match: Filter the Redis keys. Defaults to ENV.cookie_name
    """
    if match and not all(isinstance(v, str) for v in match.values()):
        raise ValueError("match values must be strings")
    async for key in redis.scan_iter(
        count=100, match=key_match or f"{MENV.COOKIE_NAME}*"
    ):
        if not isinstance(key, str):
            key = key.decode()
        sval = await redis.get(key)
        created, ses = 0, {}
        try:
            val = json.loads(sval)  # type: ignore[arg-type]
            created = int(val["created"])
            ses = val["session"]
        except Exception:
            pass
        if match:
            # Ensure we match all the supplied terms
            matches = 0
            for mkey, mval in match.items():
                if not (isinstance(ses.get(mkey), str) and mval in ses[mkey]):
                    break
                matches += 1
            if matches != len(match):
                continue
        yield key, created, ses


async def session_clean(
    redis: Redis, *, max_age: int = 90, expected_keys: dict[str, Any] | None = None
) -> None:
    """Clear session entries older than max_age days."""
    rem, keep = 0, 0
    expire = int(time.time() - max_age * 24 * 60 * 60)
    try:
        async for key, created, ses in session_iter(redis):
            all_keys = all(sk in ses for sk in (expected_keys or SES_KEYS))
            if created < expire or not all_keys:
                rem += 1
                await redis.delete(key)
            else:
                keep += 1
    finally:
        if rem:
            _LOGGER.info("Sessions removed: %s (%s total)", rem, keep)
        else:
            _LOGGER.debug("No sessions removed (%s total)", keep)


async def invalid_sessions(redis: Redis) -> None:
    """Find & clean invalid sessions."""
    async for key in redis.scan_iter(count=100, match=f"{MENV.COOKIE_NAME}*"):
        if not isinstance(key, str):
            key = key.decode()
        sval = await redis.get(key)
        if sval is None:
            continue
        try:
            val: dict = json.loads(sval)
            assert isinstance(val["created"], int)
            assert isinstance(val["session"], dict)
        except Exception as err:
            _LOGGER.warning("Removing session %s: %s", key, err)
            await redis.delete(key)


def _session_factory(key: str, created: int, session: dict) -> AsyncMSAL:
    """Create a AsyncMSAL session.

    When get_token refreshes the token retrieved from Redis, the save_cache callback
    will be responsible to update the cache in Redis.
    """

    async def async_save_cache(_: dict) -> None:
        """Save the token cache to Redis."""
        async with get_redis() as rd2:
            await rd2.set(key, json.dumps({"created": created, "session": session}))

    def save_cache(*args: Any) -> None:
        """Save the token cache to Redis."""
        try:
            asyncio.get_event_loop().create_task(async_save_cache(*args))
        except RuntimeError:
            asyncio.run(async_save_cache(*args))

    return AsyncMSAL(session, save_callback=save_cache)


async def get_session(
    email: str, *, redis: Redis | None = None, scope: str = ""
) -> AsyncMSAL:
    """Get a session from Redis."""
    cnt = 0
    async with AsyncExitStack() as stack:
        if redis is None:
            redis = await stack.enter_async_context(get_redis())
        async for key, created, session in session_iter(redis, match={"mail": email}):
            cnt += 1
            if scope and scope not in str(session.get("token_cache")).lower():
                continue
            return _session_factory(key, created, session)
    msg = f"Session for {email}"
    if not scope:
        raise ValueError(f"{msg} not found")
    raise ValueError(f"{msg} with scope {scope} not found ({cnt} checked)")


async def redis_get_json(key: str) -> list | dict | None:
    """Get a key from redis."""
    res = await MENV.database.get(key)
    if isinstance(res, str | bytes | bytearray):
        return json.loads(res)
    if res is not None:
        _LOGGER.warning("Unexpected type for %s: %s", key, type(res))
    return None


async def redis_get(key: str) -> str | None:
    """Get a key from redis."""
    res = await MENV.database.get(key)
    if isinstance(res, str):
        return res
    if isinstance(res, bytes | bytearray):
        return res.decode()
    if res is not None:
        _LOGGER.warning("Unexpected type for %s: %s", key, type(res))
    return None


async def redis_set_set(key: str, new_set: set[str]) -> None:
    """Set the value of a set in redis."""
    cur_set = set(
        s if isinstance(s, str) else s.decode()
        for s in await MENV.database.smembers(key)
    )
    dif = list(cur_set - new_set)
    if dif:
        _LOGGER.warning("%s: removing %s", key, dif)
        await MENV.database.srem(key, *dif)

    dif = list(new_set - cur_set)
    if dif:
        _LOGGER.info("%s: adding %s", key, dif)
        await MENV.database.sadd(key, *dif)


async def redis_scan(match_str: str) -> list[str]:
    """Return a list of matching keys."""
    return [
        s if isinstance(s, str) else s.decode()
        async for s in MENV.database.scan_iter(match=match_str)
    ]
