"""Settings."""
from typing import Any, Awaitable, Callable, Union

from .settings_base import SettingsBase, Var


class MSALSettings(SettingsBase):
    """Settings."""

    SP_APP_ID = Var(str, required=True)
    """SharePoint Application ID."""
    SP_APP_PW = Var(str, required=True)
    """SharePoint Application Secret."""
    SP_AUTHORITY = Var(str, required=True)
    """SharePoint Authority URL.

    Examples:
    "https://login.microsoftonline.com/common"  # For multi-tenant app
    "https://login.microsoftonline.com/Tenant_Name_or_UUID_Here"."""

    DOMAIN = "mydomain.com"
    """Your domain. Used by routes & Redis functions."""

    COOKIE_NAME = "AIOHTTP_SESSION"
    """The name of the cookie with the session identifier."""

    login_callback: list[Callable[[Any], Awaitable[Any]]] = []
    """A list of callbacks to execute on successful login."""
    info: dict[str, Callable[[Any], Union[Any, Awaitable[Any]]]] = {}
    """List of attributes to return in /user/info."""

    REDIS = "redis://redis1:6379"
    """OPTIONAL: Redis database connection used by app_init_redis_session()."""
    database: Any = None
    """Store the Redis connection when using app_init_redis_session()."""


ENV = MSALSettings()
