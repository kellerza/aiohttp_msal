"""Settings Base."""

import logging
import os
from dataclasses import Field, dataclass, fields
from pathlib import Path
from typing import Any, Literal

KEY_REQ = "required"
KEY_HIDE = "hide"
VAR_REQ_HIDE = {KEY_REQ: True, KEY_HIDE: True}
VAR_REQ = {KEY_REQ: True}
VAR_HIDE = {KEY_HIDE: True}


@dataclass
class SettingsBase:
    """Retrieve Settings from environment variables.

    Settings the appropriate environment variable, eg. to override FOOBAR,
    `export APP_FOOBAR="whatever"`.
    This is useful in production for secrets you do not wish to save in code
    and also plays nicely with docker(-compose). Settings will attempt to
    convert environment variables to match the type of the value here.
    """

    env_prefix: str = ""

    def __post_init__(self) -> None:
        """Post init."""
        fnames = {a.name for a in fields(self) if a.name.isupper()}
        if e := fnames - {a for a in dir(self) if a.isupper()}:
            raise AssertionError(f"Ensure all UPPERCASE fields has a type!: {e}")
        for fname in fnames:
            if fname.endswith("_URI") and (val := getattr(self, fname)):
                setattr(self, fname, val if val.endswith("/") else f"{val}/")

    @property
    def fields(self) -> dict[str, Field]:
        """Get fields with environment variable names as keys."""
        prefix = self.env_prefix.upper()
        return {f"{prefix}{a.name}": a for a in fields(self) if a.name.isupper()}

    def load(self, env_prefix: str | None = None) -> None:
        """Initialize."""
        logger = logging.getLogger(__name__)
        if env_prefix is not None:
            self.env_prefix = env_prefix.upper()
        for ename, atr in self.fields.items():
            newv = os.getenv(ename)
            if newv is None:
                if atr.metadata.get(KEY_REQ):
                    raise ValueError(f"Required value missing: {ename}")
                continue
            if newv.startswith('"') and newv.endswith('"'):
                newv = newv.strip('"')

            curv = getattr(self, atr.name)
            v_type: Any = atr.type or type(curv)

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
                self.env_prefix,
                atr.name,
                "***" if atr.metadata.get(KEY_HIDE) else getattr(self, atr.name),
            )

    def asdict(
        self, as_string: bool = False, hide: Literal["***"] | None = None
    ) -> dict[str, Any]:
        """Get all variables."""
        res = {}
        for ename, atr in self.fields.items():
            curv = getattr(self, atr.name)
            if atr.metadata.get(KEY_HIDE):
                if hide is None:
                    continue
                curv = "***"
            res[ename] = str(curv) if as_string else curv
        return res
