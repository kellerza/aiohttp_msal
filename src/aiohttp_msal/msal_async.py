"""AsyncIO based OAuth using the Microsoft Authentication Library (MSAL) for Python.

The AsyncMSAL class contains more info to perform OAuth & get the required tokens.
Once you have the OAuth tokens store in the session, you are free to make requests
(typically from an aiohttp server's inside a request)
"""

import asyncio
import json
from collections.abc import Callable
from functools import cached_property, partialmethod
from typing import Any, ClassVar, Literal, Unpack

import attrs
from aiohttp import web
from aiohttp.client import (
    ClientResponse,
    ClientSession,
    _RequestContextManager,
    _RequestOptions,
)
from aiohttp.typedefs import StrOrURL
from aiohttp_session import Session
from msal import ConfidentialClientApplication, SerializableTokenCache

from aiohttp_msal.settings import ENV

HttpMethods = Literal["get", "post", "put", "patch", "delete"]
HTTP_GET = "get"
HTTP_POST = "post"
HTTP_PUT = "put"
HTTP_PATCH = "patch"
HTTP_DELETE = "delete"
HTTP_ALLOWED = [HTTP_GET, HTTP_POST, HTTP_PUT, HTTP_PATCH, HTTP_DELETE]

DEFAULT_SCOPES = ["User.Read", "User.Read.All"]


# These keys will be used on the aiohttp session
TOKEN_CACHE = "token_cache"
FLOW_CACHE = "flow_cache"
USER_EMAIL = "mail"


@attrs.define()
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
    app: ConfidentialClientApplication = attrs.field(init=False)

    app_kwargs: ClassVar[dict[str, Any] | None] = None
    """ConfidentialClientApplication kwargs."""
    client_session: ClassVar[ClientSession | None] = None

    def __attrs_post_init__(self) -> None:
        """Init."""
        kwargs = dict(self.app_kwargs) if self.app_kwargs else {}
        for key, val in {
            "client_id": ENV.SP_APP_ID,
            "client_credential": ENV.SP_APP_PW,
            "authority": ENV.SP_AUTHORITY,
            "validate_authority": False,
            "token_cache": self.token_cache,
        }.items():
            kwargs.setdefault(key, val)
        self.app = ConfidentialClientApplication(**kwargs)

    @cached_property
    def token_cache(self) -> SerializableTokenCache:
        """Get the token_cache."""
        res = SerializableTokenCache()
        if self.session and self.session.get(TOKEN_CACHE):
            res.deserialize(self.session[TOKEN_CACHE])
        return res

    def save_token_cache(self) -> None:
        """Save the token cache if it changed."""
        if self.token_cache.has_state_changed:
            self.session[TOKEN_CACHE] = self.token_cache.serialize()
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
        self.session[TOKEN_CACHE] = None
        self.session[USER_EMAIL] = None
        self.session[FLOW_CACHE] = res = self.app.initiate_auth_code_flow(
            scopes or DEFAULT_SCOPES,
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
        # will raise keryerror if no cache
        auth_code_flow = self.session.pop(FLOW_CACHE)
        result = self.app.acquire_token_by_auth_code_flow(
            auth_code_flow, auth_response, scopes=scopes
        )
        if "error" in result:
            raise web.HTTPBadRequest(text=str(result["error"]))
        if "id_token_claims" not in result:
            raise web.HTTPBadRequest(text=f"Expected id_token_claims in {result}")
        self.save_token_cache()
        if tok := result.get("id_token_claims"):
            self.session[USER_EMAIL] = tok.get("preferred_username")

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
                scopes=scopes or DEFAULT_SCOPES, account=accounts[0]
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
    def mail(self) -> str:
        """User email."""
        return self.session.get(USER_EMAIL, "")

    @property
    def manager_mail(self) -> str:
        """User's manager's email."""
        return self.session.get("m_mail", "")

    @property
    def manager_name(self) -> str:
        """User's manager's name."""
        return self.session.get("m_name", "")

    @property
    def name(self) -> str:
        """User's display name."""
        return self.session.get("name", "")

    @property
    def authenticated(self) -> bool:
        """If the user is logged in."""
        return bool(self.session.get("mail"))
