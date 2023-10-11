"""aiohttp_msal."""
import logging
from functools import wraps
from inspect import getfullargspec, iscoroutinefunction
from typing import Any, Awaitable, Callable, Union

from aiohttp import ClientSession, web
from aiohttp_session import get_session
from aiohttp_session import setup as _setup

from .msal_async import AsyncMSAL
from .settings import ENV

_LOGGER = logging.getLogger(__name__)

VERSION = "0.6.5"


def msal_session(*args: Callable[[AsyncMSAL], Union[Any, Awaitable[Any]]]) -> Callable:
    """Session decorator.

    Arguments can include a list of function to perform login tests etc.
    """

    def _session(func: Callable) -> Callable:
        @wraps(func)
        async def __session(request: web.Request) -> Callable:
            _ses = AsyncMSAL(session=await get_session(request))
            for arg in args:
                if iscoroutinefunction(arg):
                    if not await arg(_ses):
                        raise web.HTTPForbidden
                elif not arg(_ses):
                    raise web.HTTPForbidden
            return await func(request=request, ses=_ses)

        assert iscoroutinefunction(func), f"Function needs to be a coroutine: {func}"
        spec = getfullargspec(func)
        assert "ses" in spec.args, f"Function needs to accept a session 'ses': {func}"
        return __session

    return _session


def authenticated(ses: AsyncMSAL) -> bool:
    """Test if session was authenticated."""
    return bool(ses.mail)


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
