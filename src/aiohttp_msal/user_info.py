"""Graph User Info."""

from aiohttp_msal.msal_async import AsyncMSAL
from aiohttp_msal.utils import retry


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
