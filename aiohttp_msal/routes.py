"""The user blueprint."""
import time
from typing import Any
from urllib.parse import urljoin

from aiohttp import web
from aiohttp_session import get_session, new_session

from aiohttp_msal.user_info import get_manager_info, get_user_info

from . import _LOGGER, COOKIE_NAME, ENV, authenticated, msal_session
from .msal_async import FLOW_CACHE, AsyncMSAL

ROUTES = web.RouteTableDef()

URI_USER_LOGIN = "/user/login"
URI_USER_AUTHORIZED = "/user/authorized"
SESSION_REDIRECT = "redirect"

# ic.disable()  # remove debug prints


def get_route(request: web.Request, url: str) -> str:
    """Retrieve server route from request.

    localhost and production on http:// with nginx proxy that adds TLS/SSL."""
    url = str(request.url.origin() / url)
    if "localhost" not in url:
        url = url.replace("p:", "ps:", 1)
    return url


@ROUTES.get(URI_USER_LOGIN)
@ROUTES.get(f"{URI_USER_LOGIN}/{{to:.+$}}")
async def user_login(request: web.Request) -> web.Response:
    """Redirect to MS login page."""
    session = await new_session(request)

    # Save redirect to use after authorized
    _to = request.headers.getone("Referer", "")  # http://localhost:3000/
    if "localhost" not in _to:
        _to = "/"
    session[SESSION_REDIRECT] = urljoin(_to, request.match_info.get("to", ""))

    msredirect = get_route(request, URI_USER_AUTHORIZED.lstrip("/"))
    redir = AsyncMSAL(session).build_auth_code_flow(redirect_uri=msredirect)
    return web.HTTPFound(redir)


@ROUTES.get(URI_USER_AUTHORIZED)
async def user_authorized(request: web.Request) -> web.Response:
    """Complete the auth code flow."""
    session = await get_session(request)
    # ic(session)

    # build a plain dict from the aiohttp server request's url parameters
    auth_response = dict(request.rel_url.query.items())

    msg = []
    response_cookie = 0

    # Ensure all expected variables were returned...
    if not all(auth_response.get(k) for k in ["code", "session_state", "state"]):
        # ic(auth_response)
        msg.append(
            f"<b>Expecting code,state,session_state in URL query params.</b> auth_response: {auth_response}"
        )

    if not request.cookies.get(COOKIE_NAME):
        # ic(request.cookies.keys())
        cookies = dict(request.cookies.items())
        msg.append(f"<b>Expecting '{COOKIE_NAME}' in cookies</b>")
        _LOGGER.fatal("Cookie should be set with Samesite:None")
        msg.append(html_table(cookies))
        try:
            response_cookie = int(request.cookies.get("RFR")) + 1
        except TypeError:
            response_cookie = 1

    elif not session.get(FLOW_CACHE):
        # ic(session)
        msg.append(f"<b>Expecting '{FLOW_CACHE}' in session</b>")
        msg.append(f"- Session.new: {session.new}")
        msg.append(html_table(session))

    aiomsal = AsyncMSAL(session)

    if not msg:
        try:
            await aiomsal.async_acquire_token_by_auth_code_flow(auth_response)
        except Exception as err:  # pylint: disable=broad-except
            msg.append(
                "<b>Could not get token</b> - async_acquire_token_by_auth_code_flow"
            )
            msg.append(str(err))

    if not msg:
        try:
            await get_user_info(aiomsal)
            await get_manager_info(aiomsal)
        except Exception as err:  # pylint: disable=broad-except
            session.pop("mail", None)
            msg.append("Could not get org info from MS graph")
            msg.append(str(err))
        else:
            for lcb in ENV.login_callback:
                await lcb(aiomsal)

    if msg:
        resp = web.Response(
            body=html_wrap("</li><li>".join(msg)),
            content_type="text/html",
        )
        if response_cookie:
            resp.set_cookie(
                COOKIE_NAME,
                "",
                path="/",
                httponly=True,
                secure=True,
                samesite="Strict",
                domain=ENV.DOMAIN,
            )
        return resp

    redirect = session.pop(SESSION_REDIRECT, "") or "/fr/"

    return web.HTTPFound(redirect)


@ROUTES.get("/user/debug")
async def user_debug(request: web.Request) -> web.Response:
    """Session test handler."""
    session = await get_session(request)
    session["debug"] = True
    debug = {
        f"cookies[{COOKIE_NAME}]": request.cookies.get(COOKIE_NAME),
        "cookies.keys()": list(request.cookies.keys()),
        # "cookies": dict(request.cookies),
        "session": str(session),
        "session.keys()": list(session.keys()),
        "ip": {
            "host": request.host,
            "ip": request.remote,
            "X-Forw-For IP": request.headers.get("X-Forwarded-For", ""),
        },
    }
    # ic(debug)
    session["debug_previous"] = time.time()
    return web.json_response(debug)


@ROUTES.get("/user/info")
@msal_session()
async def user_info(request: web.Request, ses: AsyncMSAL) -> web.Response:
    """User info handler."""
    if not authenticated(ses):
        return web.json_response({})

    debug = request.query.get("debug", False)
    res: dict[str, Any] = {
        "mail": ses.mail,
        "name": ses.name,
        "manager_mail": ses.manager_mail,
        "manager_name": ses.manager_name,
    }
    # https://docs.microsoft.com/en-us/azure/active-directory/develop/v2-permissions-and-consent
    try:
        if debug:
            res["debug"] = True
            await get_user_info(ses)
            await get_manager_info(ses)
    except RuntimeError as err:
        res["get_user_info()"] = str(err)
    return web.json_response(res)


@ROUTES.get("/user/logout")
@ROUTES.get("/user/logout/{to:.+$}")
@msal_session(authenticated)
async def user_logout(request: web.Request, ses: AsyncMSAL) -> web.Response:
    """Redirect to MS graph login page."""
    ses.session.clear()

    # post_logout_redirect_uri
    _to = request.match_info.get("to", "")
    ref = request.headers.getone("Referer", "")  # http://localhost:3000/
    if ref:
        _to = urljoin(ref, _to)
    else:
        _to = get_route(request, _to)

    return web.HTTPFound(
        "https://login.microsoftonline.com/common/oauth2/logout?"
        f"post_logout_redirect_uri={_to}"
    )  # redirect


@ROUTES.get("/user/photo")
@msal_session(authenticated)
async def user_photo(request: web.Request, ses: AsyncMSAL) -> web.Response:
    """Photo."""
    async with ses.get("https://graph.microsoft.com/v1.0/me/photo/$value") as res:
        response = web.StreamResponse(status=res.status)
        for hdr in res.headers:
            if hdr not in (
                "Etag",
                "request-id",
                "client-request-id",
                "x-ms-ags-diagnostic",
                "Date",
                "Cache-Control",
            ):
                response.headers[hdr] = res.headers[hdr]

        response.headers["Cache-Control"] = "private, max-age: 3600"

        await response.prepare(request)

        async for chunk in res.content.iter_chunked(1024):
            await response.write(chunk)

        # await response.write_eof()
        return response


def html_table(items: dict) -> str:
    """Return a table HTML."""
    res = "<table style='width:80%;border:1px solid black;'>"
    for key, val in items.items():
        res += f"<tr><td>{key}</td><td>{val}</td></tr>"
    res += "</table>"
    return res


def html_wrap(html: str) -> str:
    """Return proper HTML when login fails."""
    return f"""
    <p>Login failed. Retry at <a href='/user/login'>/user/login</a></p>

    Debug info:<ul><li>{html}

    <h2>What now?</h2>

    <p>The {ENV.DOMAIN} domain gets many cookies set by all our corporate tools.
    This causes issues with some browsers and if you get an error during login please
    clear these</p>

    <p>If you get <b>Expecting '{COOKIE_NAME}' in cookies</b> clear the cookies for
    <b>.{ENV.DOMAIN}<b> by navigating to the correct address for your browser:
    <ul>
    <li>chrome://settings/siteData?searchSubpage={ENV.DOMAIN}</li>
    <li>brave://settings/siteData?searchSubpage={ENV.DOMAIN}</li>
    <li>edge://settings/siteData</li> (you will have to search for {ENV.DOMAIN} cookies)
    </ul></p>
    """