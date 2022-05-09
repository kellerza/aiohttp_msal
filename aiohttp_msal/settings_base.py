"""Settings Base."""
import logging
import os
from pathlib import Path
from typing import Any, Type


class Var:  # pylint: disable=too-few-public-methods
    """Variable settings."""

    @staticmethod
    def from_value(val: Any):  # type: ignore
        """Ensure the return is an instance of Var."""
        return val if isinstance(val, Var) else Var(type(val))

    def __init__(
        self, var_type: Type, hidden: bool = False, required: bool = False
    ) -> None:
        """Init class."""
        self.v_type = var_type
        self.hide = hidden
        self.required = required


class SettingsBase:
    """Retrieve Settings from environment variables.

    Settings the appropriate environment variable, eg. to override FOOBAR,
    `export APP_FOOBAR="whatever"`.
    This is useful in production for secrets you do not wish to save in code
    and also plays nicely with docker(-compose). Settings will attempt to
    convert environment variables to match the type of the value here.
    """

    _vars: dict[str, Var] = {}
    _env_prefix = ""

    def load(self, environment_prefix: str = "") -> None:
        """Initialize."""
        self._env_prefix = environment_prefix
        logger = logging.getLogger(__name__)
        attrs = [a for a in dir(self) if not a.startswith("_") and a.upper() == a]
        for name in attrs:
            curv = getattr(self, name)
            newv: Any = os.getenv(environment_prefix + name.upper())
            if isinstance(curv, Var):
                self._vars[name] = curv
            info = self._vars.get(name) or Var(type(curv))
            if not newv:
                if info.required:
                    raise ValueError(f"Required value for {name} not provided")
                continue
            if newv.startswith('"') and newv.endswith('"'):
                newv = newv.strip('"')
            logger.debug("ENV %s = %s", name, "***" if info.hide else newv)

            if issubclass(info.v_type, bool):
                newv = newv.upper() in ("1", "TRUE")
            elif issubclass(info.v_type, int):
                newv = int(newv)
            elif issubclass(info.v_type, Path):
                newv = Path(newv)
            elif issubclass(info.v_type, bytes):
                newv = newv.encode()

            if name.endswith("_URI") and not newv.endswith("/"):
                newv += "/"
            setattr(self, name, newv)

    def to_dict(self, as_string: bool = False) -> dict[str, Any]:
        """Get all variables."""
        res = {}
        for name in vars(self):
            if name.startswith("_") or name.upper() != name:
                continue
            curv = getattr(self, name)
            info = self._vars.get(name) or Var(type(curv))
            if info.hide:
                continue
            res[self._env_prefix + name] = str(curv) if as_string else curv
        return res
