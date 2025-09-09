"""AsyncIO based OAuth using the Microsoft Authentication Library (MSAL) for Python.

The AsyncMSAL class contains more info to perform OAuth & get the required tokens.
Once you have the OAuth tokens store in the session, you are free to make requests
(typically from an aiohttp server's inside a request)
"""

import asyncio
import json
import logging
from collections.abc import Callable
from functools import cached_property, partialmethod
from typing import Any, ClassVar, Literal, Self, TypeVar, Unpack, cast

import attrs
from aiohttp import web
from aiohttp.client import (
    ClientResponse,
    ClientSession,
    _RequestContextManager,
    _RequestOptions,
)
from aiohttp.typedefs import StrOrURL
from aiohttp_session import Session, get_session, new_session
from msal import ConfidentialClientApplication, SerializableTokenCache

from aiohttp_msal import helpers
from aiohttp_msal.settings import ENV
from aiohttp_msal.utils import dict_property

_LOG = logging.getLogger(__name__)

HttpMethods = Literal["get", "post", "put", "patch", "delete"]
HTTP_GET = "get"
HTTP_POST = "post"
HTTP_PUT = "put"
HTTP_PATCH = "patch"
HTTP_DELETE = "delete"
HTTP_ALLOWED = [HTTP_GET, HTTP_POST, HTTP_PUT, HTTP_PATCH, HTTP_DELETE]

T = TypeVar("T")


@attrs.define(slots=False)
class AsyncMSAL:
    """AsycMSAL class.

    Authorization Code Flow Helper. Learn more about auth-code-flow at
    https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow

    Async based OAuth using the Microsoft Authentication Library (MSAL) for Python.
    Blocking MSAL functions are executed in the executor thread.
    Use until such time as MSAL Python gets a true async version.
    """

    session: Session | dict[str, Any]
    save_callback: Callable[[Session | dict[str, Any]], None] | None = None
    """Called if the token cache changes. Optional.
    Not required when the session parameter is an aiohttp_session.Session.
    """
    app_kwargs: dict[str, Any] | None = None
    """ConfidentialClientApplication kwargs."""

    client_session: ClassVar[ClientSession | None] = None
    token_cache_key: ClassVar[str] = "token_cache"
    user_email_key: ClassVar[str] = "mail"
    flow_cache_key: ClassVar[str] = "flow_cache"
    redirect_key: ClassVar[str] = "redirect"
    default_scopes: ClassVar[list[str]] = ["User.Read", "User.Read.All"]

    @classmethod
    async def from_request(
        cls,
        request: web.Request,
        /,
        allow_new: bool = False,
        app_kwargs: dict[str, Any] | None = None,
    ) -> Self:
        """Get the session or raise an exception."""
        try:
            session = await get_session(request)
            return cls(session, app_kwargs=app_kwargs)
        except TypeError as err:
            cookie = request.get(ENV.COOKIE_NAME)
            _LOG.error(
                "Invalid session, %s: %s [cookie: %s]",
                "create new" if allow_new else "fail",
                err,
                request.get(ENV.COOKIE_NAME),
                cookie,
            )
            if allow_new:
                return cls(await new_session(request), app_kwargs=app_kwargs)

            text = "Invalid session. Login for a new session: '/usr/login'"

            if not cookie:
                cookies = dict(request.cookies.items())
                text = f"Cookie empty. Expected '{ENV.COOKIE_NAME}' in cookies: {list(cookies)}. Cookie should be set with Samesite:None"

            raise web.HTTPException(text=text) from None

    @cached_property
    def app(self) -> ConfidentialClientApplication:
        """Get the app."""
        kwargs = {
            "client_id": ENV.SP_APP_ID,
            "client_credential": ENV.SP_APP_PW,
            "authority": ENV.SP_AUTHORITY,
            "validate_authority": False,
            "token_cache": self.token_cache,
        }
        if self.app_kwargs:
            kwargs.update(self.app_kwargs)
        return ConfidentialClientApplication(**kwargs)

    @cached_property
    def token_cache(self) -> SerializableTokenCache:
        """Get the token_cache."""
        res = SerializableTokenCache()
        if tc := self.session.get(self.token_cache_key):
            res.deserialize(tc)
        return res

    def save_token_cache(self) -> None:
        """Save the token cache if it changed."""
        if self.token_cache.has_state_changed:
            self.session[self.token_cache_key] = self.token_cache.serialize()
            if self.save_callback:
                self.save_callback(self.session)

    def initiate_auth_code_flow(
        self,
        redirect_uri: str,
        scopes: list[str] | None = None,
        prompt: Literal["login", "consent", "select_account", "none"] | None = None,
        **kwargs: Any,
    ) -> str:
        """First step - Start the flow."""
        self.session.pop(self.token_cache_key, None)
        self.session.pop(self.user_email_key, None)
        self.session[self.flow_cache_key] = res = self.app.initiate_auth_code_flow(
            scopes or self.default_scopes,
            redirect_uri=redirect_uri,
            response_mode="form_post",
            prompt=prompt,
            **kwargs,
            # max_age=1209600,
            # max allowed 86400 - 1 day
        )
        # https://msal-python.readthedocs.io/en/latest/#msal.ClientApplication.initiate_auth_code_flow
        return str(res["auth_uri"])

    def acquire_token_by_auth_code_flow(
        self, auth_response: Any, scopes: list[str] | None = None
    ) -> None:
        """Second step - Acquire token."""
        # Assume we have it in the cache (added by /login)
        # will raise KeyError if not in cache
        auth_code_flow = self.session.pop(self.flow_cache_key)
        result = self.app.acquire_token_by_auth_code_flow(
            auth_code_flow, auth_response, scopes=scopes
        )
        if "error" in result:
            raise web.HTTPBadRequest(text=str(result["error"]))
        if "id_token_claims" not in result:
            raise web.HTTPBadRequest(text=f"Expected id_token_claims in {result}")
        self.save_token_cache()
        if tok := result.get("id_token_claims"):
            self.session[self.user_email_key] = tok.get("preferred_username")

    async def async_acquire_token_by_auth_code_flow(self, auth_response: Any) -> None:
        """Second step - Acquire token, async version."""
        await asyncio.get_event_loop().run_in_executor(
            None, self.acquire_token_by_auth_code_flow, auth_response
        )

    def get_token(self, scopes: list[str] | None = None) -> dict[str, Any] | None:
        """Acquire a token based on username."""
        accounts = self.app.get_accounts()
        if accounts:
            result = self.app.acquire_token_silent(
                scopes=scopes or self.default_scopes, account=accounts[0]
            )
            self.save_token_cache()
            return result
        return None

    async def async_get_token(self) -> dict[str, Any] | None:
        """Acquire a token based on username."""
        return await asyncio.get_event_loop().run_in_executor(None, self.get_token)

    async def request(
        self, method: HttpMethods, url: StrOrURL, **kwargs: Unpack[_RequestOptions]
    ) -> ClientResponse:
        """Make a request to url using an oauth session.

        :param str url: url to send request to
        :param str method: type of request (get/put/post/patch/delete)
        :param kwargs: extra params to send to the request api
        :return: Response of the request
        :rtype: aiohttp.Response
        """
        token = await self.async_get_token()
        if token is None:
            raise web.HTTPClientError(text="No login token available.")

        kwargs = kwargs.copy()
        # Ensure headers exist & make a copy
        headers = dict[str, str](kwargs.get("headers") or {})  # type:ignore[arg-type]
        kwargs["headers"] = headers

        headers["Authorization"] = "Bearer " + token["access_token"]

        if method not in HTTP_ALLOWED:
            raise web.HTTPClientError(text=f"HTTP method {method} not allowed")

        if method == HTTP_GET:
            kwargs.setdefault("allow_redirects", True)
        elif method in [HTTP_POST, HTTP_PUT, HTTP_PATCH]:
            headers["Content-type"] = "application/json"
            if "data" in kwargs:
                kwargs["data"] = json.dumps(kwargs["data"])  # auto convert to json

        if not AsyncMSAL.client_session:
            AsyncMSAL.client_session = ClientSession(trust_env=True)

        return await AsyncMSAL.client_session.request(method, url, **kwargs)

    def request_ctx(
        self, method: HttpMethods, url: StrOrURL, **kwargs: Unpack[_RequestOptions]
    ) -> _RequestContextManager:
        """Request context manager."""
        return _RequestContextManager(self.request(method, url, **kwargs))

    get = partialmethod(request_ctx, HTTP_GET)
    post = partialmethod(request_ctx, HTTP_POST)

    @property
    def authenticated(self) -> bool:
        """If the user is logged in."""
        return bool(self.session.get(self.user_email_key))

    name = cast(str, dict_property("session", "name"))
    mail = dict_property("session", user_email_key)
    manager_name = dict_property("session", "m_name")
    manager_mail = dict_property("session", "m_mail")
    redirect = dict_property("session", redirect_key)

    async def async_acquire_token_by_auth_code_flow_plus(
        self,
        request: web.Request,
        get_info: Literal["user", "manager", ""] = "manager",
    ) -> tuple[bool, list[str]]:
        """Enhanced version of async_acquire_token_by_auth_code_flow. Returns issues.

        Parse the auth response from the request, checks for valid keys,
        acquire the token and get_info.

        response_mode for the auth_code flow should be "form_post"
        """
        auth_response = dict(await request.post())
        assert isinstance(self.session, Session)

        msg = list[str]()

        # Ensure all expected variables were returned...
        if not all(auth_response.get(k) for k in ["code", "session_state", "state"]):
            msg.append("Expected 'code', 'session_state', 'state' in auth_response")
            msg.append(f"Received auth_response: {list(auth_response)}")
            return False, msg

        if self.session.new:
            msg.append(
                "Warning: This is a new session and may not have all expected values."
            )

        if not self.session.get(self.flow_cache_key):
            msg.append(f"<b>Expected '{self.flow_cache_key}' in session</b>")
            msg.append(helpers.html_table(self.session))

        self.redirect = "/" + self.redirect.lstrip("/")

        if msg:
            return False, msg

        try:
            await self.async_acquire_token_by_auth_code_flow(auth_response)
        except Exception as err:
            msg.append(
                "<b>Could not get token</b> - async_acquire_token_by_auth_code_flow"
            )
            msg.append(str(err))
            return False, msg

        if not msg:
            try:
                if get_info in ("user", "manager"):
                    await helpers.get_user_info(self)
                if get_info == "manager":
                    await helpers.get_manager_info(self)
            except Exception as err:
                msg.append("Could not get org info from MS graph")
                msg.append(str(err))
                self.mail = ""
                self.name = ""

            if self.session.get("mail"):
                for lcb in ENV.login_callback:
                    await lcb(self)

        return True, msg
