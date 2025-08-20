"""Graph User Info."""

import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from aiohttp_msal.msal_async import AsyncMSAL

_T = TypeVar("_T")
_P = ParamSpec("_P")


def retry(func: Callable[_P, Awaitable[_T]]) -> Callable[_P, Awaitable[_T]]:
    """Retry if tenacity is installed."""

    @wraps(func)
    async def _retry(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        """Retry the request."""
        retries = [2, 4, 8]
        while True:
            try:
                res = await func(*args, **kwargs)
                return res
            except Exception as err:
                if retries:
                    await asyncio.sleep(retries.pop())
                else:
                    raise err

    return _retry


@retry
async def get_user_info(aiomsal: AsyncMSAL) -> None:
    """Load user info from MS graph API. Requires User.Read permissions."""
    async with aiomsal.get("https://graph.microsoft.com/v1.0/me") as res:
        body = await res.json()
        try:
            aiomsal.session["mail"] = body["mail"]
            aiomsal.session["name"] = body["displayName"]
        except KeyError as err:
            raise KeyError(
                f"Unexpected return from Graph endpoint: {body}: {err}"
            ) from err


@retry
async def get_manager_info(aiomsal: AsyncMSAL) -> None:
    """Load manager info from MS graph API. Requires User.Read.All permissions."""
    async with aiomsal.get("https://graph.microsoft.com/v1.0/me/manager") as res:
        body = await res.json()
        try:
            aiomsal.session["m_mail"] = body["mail"]
            aiomsal.session["m_name"] = body["displayName"]
        except KeyError as err:
            raise KeyError(
                f"Unexpected return from Graph endpoint: {body}: {err}"
            ) from err
