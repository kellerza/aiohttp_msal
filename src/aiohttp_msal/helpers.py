"""Graph User Info."""

from collections.abc import Mapping, Sequence
from typing import Any, Literal, TypeVar

from aiohttp import web
from aiohttp_session import get_session

from aiohttp_msal import ENV
from aiohttp_msal.msal_async import AsyncMSAL
from aiohttp_msal.utils import retry


@retry
async def get_user_info(aiomsal: AsyncMSAL) -> None:
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
async def get_manager_info(aiomsal: AsyncMSAL) -> None:
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


TA = TypeVar("TA", bound=AsyncMSAL)


async def check_auth_response(
    request: web.Request,
    asyncmsal_class: type[TA] = AsyncMSAL,  # type:ignore[assignment]
    get_info: Literal["user", "manager", ""] = "manager",
) -> tuple[TA | None, list[str]]:
    """Parse the MS auth response."""
    # Expecting response_mode="form_post"
    auth_response = dict(await request.post())

    msg = list[str]()

    # Ensure all expected variables were returned...
    if not all(auth_response.get(k) for k in ["code", "session_state", "state"]):
        msg.append("Expected 'code', 'session_state', 'state' in auth_response")
        msg.append(f"Received auth_response: {list(auth_response)}")
        return None, msg

    if not request.cookies.get(ENV.COOKIE_NAME):
        cookies = dict(request.cookies.items())
        msg.append(f"<b>Expected '{ENV.COOKIE_NAME}' in cookies</b>")
        msg.append(html_table(cookies))
        msg.append("Cookie should be set with Samesite:None")

    session = await get_session(request)
    if session.new:
        msg.append(
            "Warning: This is a new session and may not have all expected values."
        )

    if not session.get(asyncmsal_class.flow_cache_key):
        msg.append(f"<b>Expected '{asyncmsal_class.flow_cache_key}' in session</b>")
        msg.append(html_table(session))

    aiomsal = asyncmsal_class(session)
    aiomsal.redirect = "/" + aiomsal.redirect.lstrip("/")

    if msg:
        return aiomsal, msg

    try:
        await aiomsal.async_acquire_token_by_auth_code_flow(auth_response)
    except Exception as err:
        msg.append("<b>Could not get token</b> - async_acquire_token_by_auth_code_flow")
        msg.append(str(err))

    if not msg:
        try:
            if get_info in ("user", "manager"):
                await get_user_info(aiomsal)
            if get_info == "manager":
                await get_manager_info(aiomsal)
        except Exception as err:
            msg.append("Could not get org info from MS graph")
            msg.append(str(err))
            aiomsal.mail = ""
            aiomsal.name = ""

        if session.get("mail"):
            for lcb in ENV.login_callback:
                await lcb(aiomsal)

    return aiomsal, msg
