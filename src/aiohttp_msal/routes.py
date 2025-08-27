"""The user blueprint."""

import time
from collections.abc import Mapping, Sequence
from inspect import iscoroutinefunction
from typing import Any
from urllib.parse import urljoin

from aiohttp import web
from aiohttp_session import get_session, new_session

from aiohttp_msal import _LOGGER, ENV, auth_ok, msal_session
from aiohttp_msal.msal_async import FLOW_CACHE, AsyncMSAL
from aiohttp_msal.user_info import get_manager_info, get_user_info

ROUTES = web.RouteTableDef()

URI_USER_LOGIN = "/user/login"
URI_USER_AUTHORIZED = "/user/authorized"
SESSION_REDIRECT = "redirect"


def get_route(request: web.Request, url: str) -> str:
    """Retrieve server route from request.

    localhost and production on http:// with nginx proxy that adds TLS/SSL.
    """
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
    redir = AsyncMSAL(session).initiate_auth_code_flow(redirect_uri=msredirect)
    return web.HTTPFound(redir)


@ROUTES.post(URI_USER_AUTHORIZED)
async def user_authorized(request: web.Request) -> web.Response:
    """Complete the auth code flow."""
    session = await get_session(request)

    # build a plain dict from the aiohttp server request's url parameters
    # pre-0.1.18. Now we have response_mode="form_post"
    # auth_response = dict(request.rel_url.query.items())
    auth_response = dict(await request.post())

    msg = []
    response_cookie = 0

    # Ensure all expected variables were returned...
    if not all(auth_response.get(k) for k in ["code", "session_state", "state"]):
        msg.append(
            f"<b>Expecting code,state,session_state in post body.</b>auth_response: {auth_response}"
        )

    if not request.cookies.get(ENV.COOKIE_NAME):
        cookies = dict(request.cookies.items())
        msg.append(f"<b>Expecting '{ENV.COOKIE_NAME}' in cookies</b>")
        _LOGGER.fatal("Cookie should be set with Samesite:None")
        msg.append(html_table(cookies))

    elif not session.get(FLOW_CACHE):
        msg.append(f"<b>Expecting '{FLOW_CACHE}' in session</b>")
        msg.append(f"- Session.new: {session.new}")
        msg.append(html_table(session))

    aiomsal = AsyncMSAL(session)

    if not msg:
        try:
            await aiomsal.async_acquire_token_by_auth_code_flow(auth_response)
        except Exception as err:
            msg.append(
                "<b>Could not get token</b> - async_acquire_token_by_auth_code_flow"
            )
            msg.append(str(err))

    if not msg:
        session.pop("mail", None)
        session.pop("name", None)
        try:
            await get_user_info(aiomsal)
            await get_manager_info(aiomsal)
        except Exception as err:
            msg.append("Could not get org info from MS graph")
            msg.append(str(err))
        if session.get("mail"):
            for lcb in ENV.login_callback:
                await lcb(aiomsal)

    if msg:
        resp = web.Response(
            body=html_wrap(msg),
            content_type="text/html",
        )
        if response_cookie:
            resp.set_cookie(
                ENV.COOKIE_NAME,
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
        f"cookies[{ENV.COOKIE_NAME}]": request.cookies.get(ENV.COOKIE_NAME),
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
    session["debug_previous"] = time.time()
    return web.json_response(debug)


ENV.info["authenticated"] = auth_ok


@ROUTES.get("/user/info")
@msal_session()
async def user_info(request: web.Request, ses: AsyncMSAL) -> web.Response:
    """User info handler."""
    if not auth_ok(ses):
        return web.json_response({"authenticated": False})

    debug = request.query.get("debug", False)
    res: dict[str, Any] = {
        "mail": ses.mail,
        "name": ses.name,
        "manager_mail": ses.manager_mail,
        "manager_name": ses.manager_name,
    }

    for name, testf in ENV.info.items():
        if iscoroutinefunction(testf):
            res[name] = await testf(ses)
        else:
            res[name] = testf(ses)

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
@msal_session(auth_ok)
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
        f"https://login.microsoftonline.com/common/oauth2/logout?post_logout_redirect_uri={_to}"
    )  # redirect


@ROUTES.get("/user/photo")
@msal_session(auth_ok)
async def user_photo(request: web.Request, ses: AsyncMSAL) -> web.StreamResponse:
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
