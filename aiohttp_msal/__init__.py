"""aiohttp_msal."""

import logging
import typing
from functools import wraps
from inspect import getfullargspec, iscoroutinefunction

from aiohttp import ClientSession, web
from aiohttp_session import get_session
from aiohttp_session import setup as _setup

from aiohttp_msal.msal_async import AsyncMSAL
from aiohttp_msal.settings import ENV

_LOGGER = logging.getLogger(__name__)

VERSION = "0.7.1"


def msal_session(
    *callbacks: typing.Callable[[AsyncMSAL], bool | typing.Awaitable[bool]],
    at_least_one: bool | None = False,
) -> typing.Callable:
    """Session decorator.

    Arguments can include a list of function to perform login tests etc.
    """

    def _session(func: typing.Callable) -> typing.Callable:
        @wraps(func)
        async def __session(request: web.Request) -> typing.Callable:
            ses = AsyncMSAL(session=await get_session(request))
            for c_b in callbacks:
                _ok = await c_b(ses) if iscoroutinefunction(c_b) else c_b(ses)

                if at_least_one:
                    if _ok:
                        return await func(request=request, ses=ses)
                    continue

                if not _ok:
                    raise web.HTTPForbidden

            if at_least_one:
                raise web.HTTPForbidden
            return await func(request=request, ses=ses)

        assert iscoroutinefunction(func), f"Function needs to be a coroutine: {func}"
        spec = getfullargspec(func)
        assert "ses" in spec.args, f"Function needs to accept a session 'ses': {func}"
        return __session

    return _session


def auth_ok(ses: AsyncMSAL) -> bool:
    """Test if session was authenticated."""
    return bool(ses.mail)


def auth_or(
    *args: typing.Callable[[AsyncMSAL], bool | typing.Awaitable[bool]]
) -> typing.Callable[[AsyncMSAL], typing.Awaitable[bool]]:
    """Ensure either of the methods is valid. An alternative to at_least_one=True.

    Arguments can include a list of function to perform login tests etc."""

    async def or_auth(ses: AsyncMSAL) -> bool:
        """Or."""
        for arg in args:
            if iscoroutinefunction(arg):
                if await arg(ses):
                    return True
            elif arg(ses):
                return True
        raise web.HTTPForbidden

    return or_auth


async def app_init_redis_session(
    app: web.Application, max_age: int = 3600 * 24 * 90
) -> None:
    """OPTIONAL: Initialize aiohttp_session with Redis storage.

    You can initialize your own aiohttp_session & storage provider.
    """
    # pylint: disable=import-outside-toplevel
    from aiohttp_session import redis_storage
    from redis.asyncio import from_url

    await check_proxy()

    _LOGGER.info("Connect to Redis %s", ENV.REDIS)
    try:
        ENV.database = from_url(ENV.REDIS)  # pylint: disable=no-member
        # , encoding="utf-8", decode_responses=True
    except ConnectionRefusedError as err:
        raise ConnectionError("Could not connect to REDIS server") from err

    storage = redis_storage.RedisStorage(
        ENV.database,
        max_age=max_age,
        path="/",
        samesite="None",
        httponly=True,
        secure=True,
        domain=ENV.DOMAIN,
        cookie_name=ENV.COOKIE_NAME,
    )
    _setup(app, storage)


async def check_proxy() -> None:
    """Test if we have Internet connectivity through proxies etc."""
    try:
        async with ClientSession(trust_env=True) as cses:
            async with cses.get("http://httpbin.org/get") as resp:
                if resp.ok:
                    return
                raise ConnectionError(await resp.text())
    except Exception as err:  # pylint: disable=broad-except
        raise ConnectionError(
            "No connection to the Internet. Required for OAuth. Check your Proxy?"
        ) from err
