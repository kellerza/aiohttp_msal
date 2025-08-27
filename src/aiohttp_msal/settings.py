"""Settings."""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import attrs

from aiohttp_msal.settings_base import VAR_REQ, VAR_REQ_HIDE, SettingsBase

if TYPE_CHECKING:
    from redis.asyncio import Redis


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

    DOMAIN: str = attrs.field(metadata=VAR_REQ, default="")
    """Your domain. Used by routes & Redis functions."""

    COOKIE_NAME: str = "AIOHTTP_SESSION"
    """The name of the cookie with the session identifier."""

    login_callback: list[Callable[[Any], Awaitable[Any]]] = attrs.field(factory=list)
    """A list of callbacks to execute on successful login."""
    info: dict[str, Callable[[Any], Any | Awaitable[Any]]] = attrs.field(factory=dict)
    """List of attributes to return in /user/info."""

    REDIS: str = "redis://redis1:6379"
    """OPTIONAL: Redis database connection used by app_init_redis_session()."""
    database: "Redis" = attrs.field(init=False)
    """Store the Redis connection when using app_init_redis_session()."""


ENV = MSALSettings()
