"""Settings."""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from aiohttp_msal.settings_base import VAR_HIDE, VAR_REQ, VAR_REQ_HIDE, SettingsBase

if TYPE_CHECKING:
    from redis.asyncio import Redis

__all__ = ["ENV", "VAR_HIDE", "VAR_REQ", "VAR_REQ_HIDE", "MSALSettings", "SettingsBase"]


@dataclass
class MSALSettings(SettingsBase):
    """Settings."""

    SP_APP_ID: str = field(metadata=VAR_REQ, default="")
    """SharePoint Application ID."""
    SP_APP_PW: str = field(metadata=VAR_REQ_HIDE, default="")
    """SharePoint Application Secret."""
    SP_AUTHORITY: str = field(metadata=VAR_REQ, default="")
    """SharePoint Authority URL.

    Examples:
    "https://login.microsoftonline.com/common"  # For multi-tenant app
    "https://login.microsoftonline.com/Tenant_Name_or_UUID_Here"."""

    DOMAIN: str = field(metadata=VAR_REQ, default="")
    """Your domain. Used by routes & Redis functions."""

    COOKIE_NAME: str = "AIOHTTP_SESSION"
    """The name of the cookie with the session identifier."""

    login_callback: list[Callable[[Any], Awaitable[Any]]] = field(default_factory=list)
    """A list of callbacks to execute on successful login."""
    info: dict[str, Callable[[Any], Any | Awaitable[Any]]] = field(default_factory=dict)
    """List of attributes to return in /user/info."""

    REDIS: str = "redis://redis1:6379"
    """OPTIONAL: Redis database connection used by app_init_redis_session()."""
    database: "Redis" = None  # type: ignore[assignment]
    """Store the Redis connection when using app_init_redis_session()."""

    json_dumps: Callable[[Any], str] = field(default=json.dumps)
    json_loads: Callable[[str | bytes | bytearray], Any] = field(default=json.loads)


ENV = MSALSettings("MSAL")
