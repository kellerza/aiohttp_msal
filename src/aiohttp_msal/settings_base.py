"""Settings Base."""

import logging
import os
from pathlib import Path
from typing import Any

import attrs

KEY_REQ = "required"
KEY_HIDE = "hide"
VAR_REQ_HIDE = {KEY_REQ: True, KEY_HIDE: True}
VAR_REQ = {KEY_REQ: True}
VAR_HIDE = {KEY_HIDE: True}


@attrs.define
class SettingsBase:
    """Retrieve Settings from environment variables.

    Settings the appropriate environment variable, eg. to override FOOBAR,
    `export APP_FOOBAR="whatever"`.
    This is useful in production for secrets you do not wish to save in code
    and also plays nicely with docker(-compose). Settings will attempt to
    convert environment variables to match the type of the value here.
    """

    _env_prefix: str = attrs.field(init=False, default="")

    def _get_fields(self) -> dict[str, attrs.Attribute]:
        """Get env."""
        res: list[attrs.Attribute] = [
            a for a in attrs.fields(self.__class__) if a.name.isupper()
        ]

        dirs = [f for f in dir(self) if f.isupper()]
        if len(dirs) != len(res):
            for atr in res:
                dirs.remove(atr.name)
            raise AssertionError(f"There are UPPERCASE fields without a type!: {dirs}")

        return {f"{self._env_prefix}{a.name}": a for a in res}

    def load(self, environment_prefix: str = "") -> None:
        """Initialize."""
        logger = logging.getLogger(__name__)
        self._env_prefix = environment_prefix.upper()
        for ename, atr in self._get_fields().items():
            newv = os.getenv(ename)
            if newv is None:
                if atr.metadata.get(KEY_REQ):
                    raise ValueError(f"Required value missing: {ename}")
                continue
            if newv.startswith('"') and newv.endswith('"'):
                newv = newv.strip('"')

            curv = getattr(self, atr.name)
            v_type = atr.type or type(curv)

            if issubclass(v_type, bool):
                setattr(self, atr.name, newv.upper() in ("1", "TRUE"))
            elif issubclass(v_type, int):
                setattr(self, atr.name, int(newv))
            elif issubclass(v_type, Path):
                setattr(self, atr.name, Path(newv))
            elif issubclass(v_type, bytes):
                setattr(self, atr.name, newv.encode())
            else:
                if atr.name.endswith("_URI") and not newv.endswith("/"):
                    newv += "/"
                setattr(self, atr.name, newv)

            logger.debug(
                "ENV %s%s = %s",
                self._env_prefix,
                atr.name,
                "***" if atr.metadata.get(KEY_HIDE) else getattr(self, atr.name),
            )

    def asdict(self, as_string: bool = False) -> dict[str, Any]:
        """Get all variables."""
        res = {}
        for ename, atr in self._get_fields().items():
            curv = getattr(self, atr.name)
            if atr.metadata.get(KEY_HIDE):
                continue
            res[ename] = str(curv) if as_string else curv
        return res
