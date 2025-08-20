"""aiohttp_msal."""

import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from inspect import getfullargspec, iscoroutinefunction
from typing import TypeVar, TypeVarTuple, cast

from aiohttp import ClientSession, web
from aiohttp_session import get_session
from aiohttp_session import setup as _setup

from aiohttp_msal.msal_async import AsyncMSAL
from aiohttp_msal.settings import ENV

_LOGGER = logging.getLogger(__name__)

_T = TypeVar("_T")
Ts = TypeVarTuple("Ts")


def msal_session(
    *callbacks: Callable[[AsyncMSAL], bool | Awaitable[bool]],
    at_least_one: bool | None = False,
) -> Callable[
    [Callable[[*Ts, AsyncMSAL], Awaitable[_T]]], Callable[[*Ts], Awaitable[_T]]
]:
    """Session decorator.

    Arguments can include a list of function to perform login tests etc.
    """

    def check_session(
        func: Callable[[*Ts, AsyncMSAL], Awaitable[_T]],
    ) -> Callable[[*Ts], Awaitable[_T]]:
        @wraps(func)
        async def wrapper(*args: *Ts) -> _T:
            if len(args) < 1:
                raise AssertionError("Requires a Request as the first parameter")
            request = cast(web.Request, args[0])
            ses = AsyncMSAL(session=await get_session(request))
            for c_b in callbacks:
                _ok = await c_b(ses) if iscoroutinefunction(c_b) else c_b(ses)

                if at_least_one:
                    if _ok:
                        return await func(*args, ses)
                elif not _ok:
                    raise web.HTTPForbidden

            if at_least_one:
                raise web.HTTPForbidden
            return await func(*args, ses)

        assert iscoroutinefunction(func), f"Function needs to be a coroutine: {func}"
        spec = getfullargspec(func)
        assert "ses" in spec.args, f"Function needs to accept a session 'ses': {func}"
        return wrapper

    return check_session


def auth_ok(ses: AsyncMSAL) -> bool:
    """Test if session was authenticated."""
    return bool(ses.mail)


def auth_or(
    *args: Callable[[AsyncMSAL], bool | Awaitable[bool]],
) -> Callable[[AsyncMSAL], Awaitable[bool]]:
    """Ensure either of the methods is valid. An alternative to at_least_one=True.

    Arguments can include a list of function to perform login tests etc.
    """

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
    """Init an aiohttp_session with Redis storage helper.

    You can initialize your own aiohttp_session & storage provider.
    """
    from aiohttp_session import redis_storage
    from redis.asyncio import from_url

    await check_proxy()

    _LOGGER.info("Connect to Redis %s", ENV.REDIS)
    try:
        ENV.database = from_url(ENV.REDIS)
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
    except Exception as err:
        raise ConnectionError(
            "No connection to the Internet. Required for OAuth. Check your Proxy?"
        ) from err
