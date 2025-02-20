"""Settings."""

# pylint:disable=invalid-name
import typing as t

import attrs

from aiohttp_msal.settings_base import VAR_REQ, VAR_REQ_HIDE, SettingsBase

if t.TYPE_CHECKING:
    from redis.asyncio import Redis
else:
    Redis = None


@attrs.define
class MSALSettings(SettingsBase):
    """Settings."""

    SP_APP_ID: str = attrs.field(metadata=VAR_REQ, default="")
    """SharePoint Application ID."""
    SP_APP_PW: str = attrs.field(metadata=VAR_REQ_HIDE, default="")
    """SharePoint Application Secret."""
    SP_AUTHORITY: str = attrs.field(metadata=VAR_REQ, default="")
    """SharePoint Authority URL.

    Examples:
    "https://login.microsoftonline.com/common"  # For multi-tenant app
    "https://login.microsoftonline.com/Tenant_Name_or_UUID_Here"."""

    DOMAIN = "mydomain.com"
    """Your domain. Used by routes & Redis functions."""

    COOKIE_NAME = "AIOHTTP_SESSION"
    """The name of the cookie with the session identifier."""

    login_callback: list[t.Callable[[t.Any], t.Awaitable[t.Any]]] = []
    """A list of callbacks to execute on successful login."""
    info: dict[str, t.Callable[[t.Any], t.Any | t.Awaitable[t.Any]]] = {}
    """List of attributes to return in /user/info."""

    REDIS = "redis://redis1:6379"
    """OPTIONAL: Redis database connection used by app_init_redis_session()."""
    database: Redis = None  # type: ignore
    """Store the Redis connection when using app_init_redis_session()."""


ENV = MSALSettings()
