"""Settings."""
from typing import Any, Awaitable, Callable

from .settings_base import SettingsBase, Var


class MSALSettings(SettingsBase):
    """Settings"""

    SP_APP_ID = Var(str, required=True)
    SP_APP_PW = Var(str, required=True)
    SP_AUTHORITY = Var(str, required=True)

    REDIS = "redis://redis1:6379"
    DOMAIN = "mydomain.com"

    database: Any = None
    login_callback: list[Callable[[Any], Awaitable[Any]]] = []


ENV = MSALSettings()
