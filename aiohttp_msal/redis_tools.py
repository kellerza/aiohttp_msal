"""Redis tools for sessions."""
import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Optional

from redis.asyncio import Redis, from_url

from aiohttp_msal.msal_async import AsyncMSAL
from aiohttp_msal.settings import ENV

_LOGGER = logging.getLogger(__name__)

SES_KEYS = ("mail", "name", "m_mail", "m_name")


def get_redis() -> Redis:
    """Get a Redis connection."""
    _LOGGER.info("Connect to Redis %s", ENV.REDIS)
    ENV.database = from_url(ENV.REDIS)  # pylint: disable=no-member
    return ENV.database


async def iter_redis(
    redis: Redis, *, clean: bool = False, match: Optional[dict[str, str]] = None
) -> AsyncGenerator[tuple[str, str, dict], None]:
    """Iterate over the Redis keys to find a specific session."""
    async for key in redis.scan_iter(count=100, match=f"{ENV.COOKIE_NAME}*"):
        sval = await redis.get(key)
        if not isinstance(sval, str):
            if clean:
                await redis.delete(key)
            continue
        val = json.loads(sval)
        ses = val.get("session")
        created = val.get("created")
        if clean and not ses or not created:
            await redis.delete(key)
            continue
        if match:
            for mkey, mval in match.items():
                if mval not in ses[mkey]:
                    continue
        created = val.get("created") or "0"
        session = val.get("session") or {}
        yield key, created, session


async def clean_redis(redis: Redis, max_age: int = 90) -> None:
    """Clear session entries older than max_age days."""
    expire = int(time.time() - max_age * 24 * 60 * 60)
    async for key, created, ses in iter_redis(redis, clean=True):
        for key in SES_KEYS:
            if not ses.get(key):
                await redis.delete(key)
                continue
        if int(created) < expire:
            await redis.delete(key)


def _session_factory(key: str, created: str, session: dict) -> AsyncMSAL:
    """Create a session with a save callback."""

    async def async_save_cache(_: dict) -> None:
        """Save the token cache to Redis."""
        rd2 = get_redis()
        try:
            await rd2.set(key, json.dumps({"created": created, "session": session}))
        finally:
            await rd2.close()

    def save_cache(*args: Any) -> None:
        """Save the token cache to Redis."""
        try:
            asyncio.get_event_loop().create_task(async_save_cache(*args))
        except RuntimeError:
            asyncio.run(async_save_cache(*args))

    return AsyncMSAL(session, save_cache=save_cache)


async def get_session(red: Redis, email: str) -> AsyncMSAL:
    """Get a session from Redis."""
    async for key, created, session in iter_redis(red, match={"mail": email}):
        return _session_factory(key, created, session)
    raise ValueError(f"Session for {email} not found")
