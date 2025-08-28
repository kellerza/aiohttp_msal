"""The user blueprint."""

import time
from inspect import iscoroutinefunction
from typing import Any
from urllib.parse import urljoin

from aiohttp import web
from aiohttp_session import get_session, new_session

from aiohttp_msal import ENV, auth_ok, msal_session
from aiohttp_msal.helpers import (
    check_auth_response,
    get_manager_info,
    get_user_info,
    html_wrap,
)
from aiohttp_msal.msal_async import AsyncMSAL

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
        url = url.replace("http:", "https:", 1)
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
    raise web.HTTPFound(redir)


@ROUTES.post(URI_USER_AUTHORIZED)
async def user_authorized(request: web.Request) -> web.Response:
    """Complete the auth code flow."""
    aiomsal, msg = await check_auth_response(request, AsyncMSAL)

    if aiomsal and not msg:
        try:
            raise web.HTTPFound(aiomsal.redirect)
        finally:
            aiomsal.redirect = ""

    resp = web.Response(
        body=html_wrap(msg),
        content_type="text/html",
    )
    if aiomsal is None:
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
