"""Graph User Info."""
import asyncio
from functools import wraps
from typing import Any, Callable

from .msal_async import AsyncMSAL


def retry(func: Callable) -> Callable:
    """Retry if tenacity is installed."""

    @wraps(func)
    async def _retry(*args: Any, **kwargs: Any) -> Any:
        """Retry the request."""
        retries = [2, 4, 8]
        while True:
            try:
                res = await func(*args, **kwargs)
                return res
            except Exception as err:  # pylint: disable=broad-except
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
