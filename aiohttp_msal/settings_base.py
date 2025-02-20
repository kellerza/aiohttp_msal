"""Settings Base."""

import logging
import os
import typing as t
from pathlib import Path

import attrs

KEY_REQ = "required"
KEY_HIDE = "hide"
VAR_REQ_HIDE = {KEY_REQ: True, KEY_HIDE: True}
VAR_REQ = {KEY_REQ: True}
VAR_HIDE = {KEY_HIDE: True}


def _is_hidden(atr: attrs.Attribute) -> bool:
    """Is this field hidden."""
    return bool(atr.metadata.get(KEY_HIDE))


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
        fields: tuple[attrs.Attribute, ...] = attrs.fields(self.__class__)
        return {f"{self._env_prefix}{a.name}": a for a in fields if a.name.isupper()}

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

    def to_dict(self, as_string: bool = False) -> dict[str, t.Any]:
        """Get all variables."""
        res = {}
        for ename, atr in self._get_fields().items():
            curv = getattr(self, atr.name)
            if atr.metadata.get(KEY_HIDE):
                continue
            res[ename] = str(curv) if as_string else curv
        return res

    def __attrs_post_init__(self) -> None:
        """Ensure the class is ok."""
        afields = [a.name for a in self._get_fields().values()]
        fields = [f for f in dir(self) if f.isupper() and f not in afields]
        if fields:
            raise AssertionError(f"There are UPPERCASE fields without a type!: {fields}")
