"""Graph User Info."""

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from aiohttp import web

from aiohttp_msal.settings import ENV
from aiohttp_msal.utils import retry

if TYPE_CHECKING:
    from aiohttp_msal.msal_async import AsyncMSAL


@retry
async def get_user_info(aiomsal: "AsyncMSAL") -> None:
    """Load user info from MS graph API. Requires User.Read permissions."""
    async with aiomsal.get("https://graph.microsoft.com/v1.0/me") as res:
        body = await res.json()
        try:
            aiomsal.mail = body["mail"]
            aiomsal.name = body["displayName"]
        except KeyError as err:
            raise KeyError(
                f"Unexpected return from Graph endpoint: {body}: {err}"
            ) from err


@retry
async def get_manager_info(aiomsal: "AsyncMSAL") -> None:
    """Load manager info from MS graph API. Requires User.Read.All permissions."""
    async with aiomsal.get("https://graph.microsoft.com/v1.0/me/manager") as res:
        body = await res.json()
        try:
            aiomsal.manager_mail = body["mail"]
            aiomsal.manager_name = body["displayName"]
        except KeyError as err:
            raise KeyError(
                f"Unexpected return from Graph endpoint: {body}: {err}"
            ) from err


def html_table(items: Mapping[Any, Any]) -> str:
    """Return a table HTML."""
    res = "<table style='width:80%;border:1px solid black;'>"
    for key, val in items.items():
        res += f"<tr><td>{key}</td><td>{val}</td></tr>"
    res += "</table>"
    return res


def html_wrap(msgs: Sequence[str]) -> str:
    """Return proper HTML when login fails."""
    html = "</li><li>".join(msgs)
    return f"""
    <h2>Login failed</h2>

    <p>Retry at <a href='/user/login'>/user/login</a></p>

    <p>Try clearing the cookies for <b>.{ENV.DOMAIN}<b> by navigating to the correct
    address for your browser:
    <ul>
    <li>chrome://settings/siteData?searchSubpage={ENV.DOMAIN}</li>
    <li>brave://settings/siteData?searchSubpage={ENV.DOMAIN}</li>
    <li>edge://settings/siteData (you will have to search for {ENV.DOMAIN} cookies)</li>
    </ul></p>

    <h4>Debug info</h4>
    <ul><li>{html}</li></ul>
    """


def get_url(request: web.Request, path: str = "", https_proxy: bool = True) -> str:
    """Return the full outside URL."""
    res = str(request.url.with_path(path))
    return res.replace("http://", "https://") if https_proxy else res
