"""Redis tools for sessions."""
import asyncio
import json
import logging
import time
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncGenerator, Optional

from redis.asyncio import Redis, from_url

from aiohttp_msal.msal_async import AsyncMSAL
from aiohttp_msal.settings import ENV

_LOGGER = logging.getLogger(__name__)

SES_KEYS = ("mail", "name", "m_mail", "m_name")


@asynccontextmanager
async def get_redis() -> AsyncGenerator[Redis, None]:
    """Get a Redis connection."""
    if ENV.database:
        _LOGGER.debug("Using redis from environment")
        yield ENV.database
        return
    _LOGGER.info("Connect to Redis %s", ENV.REDIS)
    redis = from_url(ENV.REDIS)
    try:
        yield redis
    finally:
        await redis.close()


async def session_iter(
    redis: Redis,
    *,
    match: Optional[dict[str, str]] = None,
    key_match: Optional[str] = None,
) -> AsyncGenerator[tuple[str, int, dict[str, Any]], None]:
    """Iterate over the Redis keys to find a specific session.

    match: Filter based on session content (i.e. mail/name)
    key_match: Filter the Redis keys. Defaults to ENV.cookie_name
    """
    async for key in redis.scan_iter(
        count=100, match=key_match or f"{ENV.COOKIE_NAME}*"
    ):
        sval = await redis.get(key)
        created, ses = 0, {}
        try:
            val = json.loads(sval)  # type: ignore
            created = int(val["created"])
            ses = val["session"]
        except Exception:  # pylint: disable=broad-except
            pass
        if match:
            # Ensure we match all the supplied terms
            if not all(k in ses and v in ses[k] for k, v in match.items()):
                continue
        yield key, created, ses


async def session_clean(
    redis: Redis, *, max_age: int = 90, expected_keys: Optional[dict] = None
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


def _session_factory(key: str, created: str, session: dict) -> AsyncMSAL:
    """Create a AsyncMSAL session.

    When get_token refreshes the token retrieved from Redis, the save_cache callback
    will be responsible to update the cache in Redis."""

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

    return AsyncMSAL(session, save_cache=save_cache)


async def get_session(email: str, *, redis: Optional[Redis] = None) -> AsyncMSAL:
    """Get a session from Redis."""
    async with AsyncExitStack() as stack:
        if redis is None:
            redis = await stack.enter_async_context(get_redis())
        async for key, created, session in session_iter(redis, match={"mail": email}):
            return _session_factory(key, str(created), session)
    raise ValueError(f"Session for {email} not found")
