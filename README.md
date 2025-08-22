# Async based MSAL helper for aiohttp - aiohttp_msal Python library

Authorization Code Flow Helper. Learn more about auth-code-flow at
<https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow>

Async based OAuth using the Microsoft Authentication Library (MSAL) for Python.

Blocking MSAL functions are executed in the executor thread.
Should be useful until such time as MSAL Python gets a true async version.

Tested with MSAL Python 1.21.0 onward - [MSAL Python docs](https://github.com/AzureAD/microsoft-authentication-library-for-python)

## AsycMSAL class

The AsyncMSAL class wraps the behavior in the following example app
<https://github.com/Azure-Samples/ms-identity-python-webapp/blob/master/app.py#L76>

It is responsible to manage tokens & token refreshes and as a client to retrieve data using these tokens.

### Acquire the token

Firstly you should get the tokens via OAuth

1. `initiate_auth_code_flow` [referernce](https://msal-python.readthedocs.io/en/latest/#msal.PublicClientApplication.initiate_auth_code_flow)

    The caller is expected to:
    1. somehow store this content, typically inside the current session of the server,
    2. guide the end user (i.e. resource owner) to visit that auth_uri, typically with a redirect
    3. and then relay this dict and subsequent auth response to
        acquire_token_by_auth_code_flow().

    **Step 1** and part of **Step 3** is stored by this class in the aiohttp_session

2. `acquire_token_by_auth_code_flow` [referernce](https://msal-python.readthedocs.io/en/latest/#msal.PublicClientApplication.initiate_auth_code_flow)

### Use the token

Now you are free to make requests (typically from an aiohttp server)

```python
session = await get_session(request)
aiomsal = AsyncMSAL(session)
async with aiomsal.get("https://graph.microsoft.com/v1.0/me") as res:
    res = await res.json()
```

## Example web server

Complete routes can be found in [routes.py](./aiohttp_msal/routes.py)

### Start the login process

```python
@ROUTES.get("/user/login")
async def user_login(request: web.Request) -> web.Response:
    """Redirect to MS login page."""
    session = await new_session(request)

    redir = AsyncMSAL(session).build_auth_code_flow(
        redirect_uri=get_route(request, URI_USER_AUTHORIZED)
    )

    return web.HTTPFound(redir)
```

### Acquire the token after being redirected back to the server

```python
@ROUTES.post(URI_USER_AUTHORIZED)
async def user_authorized(request: web.Request) -> web.Response:
    """Complete the auth code flow."""
    session = await get_session(request)
    auth_response = dict(await request.post())

    aiomsal = AsyncMSAL(session)
    await aiomsal.async_acquire_token_by_auth_code_flow(auth_response)
```

## Helper methods

- `@ROUTES.get("/user/photo")`

  Serve the user's photo from their Microsoft profile

- `get_user_info`

  Get the user's email and display name from MS Graph

- `get_manager_info`

  Get the user's manager info from MS Graph

## Redis tools to retrieve session tokens

```python
from aiohttp_msal import ENV, AsyncMSAL
from aiohttp_msal.redis_tools import get_session

def main()
    # Uses the redis.asyncio driver to retrieve the current token
    # Will update the token_cache if a RefreshToken was used
    ses = asyncio.run(get_session(MYEMAIL))
    client = GraphClient(ses.get_token)
    # ...
    # use the Graphclient
```

## Development

```bash
uv sync --all-extras
uv tool install ruff
uv tool install codespell
uv tool install pyproject-fmt
```
