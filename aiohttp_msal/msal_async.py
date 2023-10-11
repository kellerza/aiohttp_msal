"""AsyncIO based OAuth using the Microsoft Authentication Library (MSAL) for Python.

The AsyncMSAL class contains more info to perform OAuth & get the required tokens.
Once you have the OAuth tokens store in the session, you are free to make requests
(typically from an aiohttp server's inside a request)
"""
import asyncio
import json
from functools import partial, wraps
from typing import Any, Callable, Optional, Union

from aiohttp import web
from aiohttp.client import ClientResponse, ClientSession, _RequestContextManager
from aiohttp_session import Session
from msal import ConfidentialClientApplication, SerializableTokenCache

from .settings import ENV

HTTP_GET = "get"
HTTP_POST = "post"
HTTP_PUT = "put"
HTTP_PATCH = "patch"
HTTP_DELETE = "delete"
HTTP_ALLOWED = [HTTP_GET, HTTP_POST, HTTP_PUT, HTTP_PATCH, HTTP_DELETE]

DEFAULT_SCOPES = ["User.Read", "User.Read.All"]


def async_wrap(func: Callable) -> Callable:
    """Wrap a function doing I/O to run in an executor thread."""

    @wraps(func)
    async def run(
        *args: Any,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        executor: Any = None,
        **kwargs: dict[str, Any],
    ) -> Callable:
        if loop is None:
            loop = asyncio.get_event_loop()
        pfunc = partial(func, *args, **kwargs)
        return await loop.run_in_executor(executor, pfunc)

    return run


# These keys will be used on the aiohttp session
TOKEN_CACHE = "token_cache"
FLOW_CACHE = "flow_cache"
USER_EMAIL = "mail"


class AsyncMSAL:
    """AsycMSAL class.

    AsyncIO based OAuth using the Microsoft Authentication Library (MSAL) for Python.
    Blocking MSAL functions are executed in the executor thread.
    Use until such time as MSAL Python gets a true async version...

    Tested with MSAL Python 1.13.0
    https://github.com/AzureAD/microsoft-authentication-library-for-python

    AsyncMSAL is based on the following example app
    https://github.com/Azure-Samples/ms-identity-python-webapp/blob/master/app.py#L76

    Use as follows:

        Get the tokens via oauth

        1. initiate_auth_code_flow
           https://msal-python.readthedocs.io/en/latest/#msal.ClientApplication.initiate_auth_code_flow

           The caller is expected to:
           1. somehow store this content, typically inside the current session of the
              server,
           2. guide the end user (i.e. resource owner) to visit that auth_uri,
              typically with a redirect
           3. and then relay this dict and subsequent auth response to
              acquire_token_by_auth_code_flow().

           [1. and part of 3.] is stored by this class in the aiohttp_session

        2. acquire_token_by_auth_code_flow
           https://msal-python.readthedocs.io/en/latest/#msal.ClientApplication.acquire_token_by_auth_code_flow


        Now you are free to make requests (typically from an aiohttp server)

            session = await get_session(request)
            aiomsal = AsyncMSAL(session)
            async with aiomsal.get("https://graph.microsoft.com/v1.0/me") as res:
                res = await res.json()

    """

    _token_cache: SerializableTokenCache = None
    _app: ConfidentialClientApplication = None
    _clientsession: ClientSession = None  # type: ignore

    def __init__(
        self,
        session: Union[Session, dict[str, str]],
        save_cache: Optional[Callable[[Union[Session, dict[str, str]]], None]] = None,
    ):
        """Init the class.

        **save_token_cache** will be called if the token cache changes. Optional.
          Not required when the session parameter is an aiohttp_session.Session.
        """
        self.session = session
        if save_cache:
            self.save_token_cache = save_cache
        if not isinstance(session, (Session, dict)):
            raise ValueError(f"session or dict-like object required {session}")

    @property
    def token_cache(self) -> SerializableTokenCache:
        """Get the token_cache."""
        if not self._token_cache:
            self._token_cache = SerializableTokenCache()
            # _load_token_cache
            if self.session and self.session.get(TOKEN_CACHE):
                self._token_cache.deserialize(self.session[TOKEN_CACHE])

        return self._token_cache

    @property
    def app(self) -> ConfidentialClientApplication:
        """Create the application using the cache.

        Based on: https://github.com/Azure-Samples/ms-identity-python-webapp/blob/master/app.py#L76
        """
        if not self._app:
            token_cache = self.token_cache
            self._app = ConfidentialClientApplication(
                client_id=ENV.SP_APP_ID,
                client_credential=ENV.SP_APP_PW,
                authority=ENV.SP_AUTHORITY,  # common/oauth2/v2.0/token'
                validate_authority=False,
                token_cache=token_cache,
            )
        return self._app

    def _save_token_cache(self) -> None:
        """Save the token cache if it changed."""
        if self.token_cache.has_state_changed:
            self.session[TOKEN_CACHE] = self.token_cache.serialize()
            if hasattr(self, "save_token_cache"):
                self.save_token_cache(self.token_cache)

    def build_auth_code_flow(
        self, redirect_uri: str, scopes: Optional[list[str]] = None
    ) -> str:
        """First step - Start the flow."""
        self.session[TOKEN_CACHE] = None  # type: ignore
        self.session[USER_EMAIL] = None  # type: ignore
        self.session[FLOW_CACHE] = res = self.app.initiate_auth_code_flow(
            scopes or DEFAULT_SCOPES,
            redirect_uri=redirect_uri,
            response_mode="form_post"
            # max_age=1209600,
            # max allowed 86400 - 1 day
        )
        # https://msal-python.readthedocs.io/en/latest/#msal.ClientApplication.initiate_auth_code_flow
        return str(res["auth_uri"])

    def acquire_token_by_auth_code_flow(self, auth_response: Any) -> None:
        """Second step - Acquire token."""
        # Assume we have it in the cache (added by /login)
        # will raise keryerror if no cache
        auth_code_flow = self.session.pop(FLOW_CACHE)
        result = self.app.acquire_token_by_auth_code_flow(auth_code_flow, auth_response)
        if "error" in result:
            raise web.HTTPBadRequest(text=str(result["error"]))
        if "id_token_claims" not in result:
            raise web.HTTPBadRequest(text=f"Expected id_token_claims in {result}")
        self._save_token_cache()
        self.session[USER_EMAIL] = result.get("id_token_claims").get(
            "preferred_username"
        )

    async def async_acquire_token_by_auth_code_flow(self, auth_response: Any) -> None:
        """Second step - Acquire token, async version."""
        await asyncio.get_event_loop().run_in_executor(
            None, self.acquire_token_by_auth_code_flow, auth_response
        )

    def get_token(self, scopes: Optional[list[str]] = None) -> Optional[dict[str, Any]]:
        """Acquire a token based on username."""
        accounts = self.app.get_accounts()
        if accounts:
            result = self.app.acquire_token_silent(
                scopes=scopes or DEFAULT_SCOPES, account=accounts[0]
            )
            self._save_token_cache()
            return result
        return None

    async def async_get_token(self) -> Optional[dict[str, Any]]:
        """Acquire a token based on username."""
        return await asyncio.get_event_loop().run_in_executor(None, self.get_token)

    async def request(self, method: str, url: str, **kwargs: Any) -> ClientResponse:
        """Make a request to url using an oauth session.

        :param str url: url to send request to
        :param str method: type of request (get/put/post/patch/delete)
        :param kwargs: extra params to send to the request api
        :return: Response of the request
        :rtype: aiohttp.Response
        """
        if not self._clientsession:
            AsyncMSAL._clientsession = ClientSession(trust_env=True)

        token = await self.async_get_token()
        if token is None:
            raise web.HTTPClientError(text="No login token available.")

        kwargs = kwargs.copy()
        # Ensure headers exist & make a copy
        kwargs["headers"] = headers = dict(kwargs.get("headers", {}))

        headers["Authorization"] = "Bearer " + token["access_token"]

        if method not in HTTP_ALLOWED:
            raise web.HTTPClientError(text=f"HTTP method {method} not allowed")

        if method == HTTP_GET:
            kwargs.setdefault("allow_redirects", True)
        elif method in [HTTP_POST, HTTP_PUT, HTTP_PATCH]:
            headers["Content-type"] = "application/json"
            if "data" in kwargs:
                kwargs["data"] = json.dumps(kwargs["data"])  # auto convert to json

        response = await self._clientsession.request(method, url, **kwargs)

        return response

    def get(self, url: str, **kwargs: Any):  # type:ignore
        """GET Request."""
        return _RequestContextManager(self.request(HTTP_GET, url, **kwargs))

    def post(self, url: str, **kwargs: Any):  # type:ignore
        """POST request."""
        return _RequestContextManager(self.request(HTTP_POST, url, **kwargs))

    @property
    def mail(self) -> str:
        """User email."""
        return self.session.get("mail", "")

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
