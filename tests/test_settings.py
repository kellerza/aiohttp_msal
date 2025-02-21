"""Test settings."""

from pathlib import Path

import attrs
import pytest

from aiohttp_msal.settings import ENV, VAR_REQ, SettingsBase


def test_load() -> None:
    """Load."""
    # see env in pyproject.toml
    assert ENV.DOMAIN == "mydomain.com"

    ENV.load("X_")
    assert ENV.SP_APP_ID == "i1"
    assert ENV.SP_APP_PW == "p1"

    ENV.load("Y_")
    assert ENV.asdict() == {
        "Y_COOKIE_NAME": "AIOHTTP_SESSION",
        "Y_DOMAIN": "mydomain.com",
        "Y_REDIS": "redis://redis1:6379",
        "Y_SP_APP_ID": "i2",
        # "Y_SP_APP_PW": "p2", # hidden!
        "Y_SP_AUTHORITY": "a2",
    }


@attrs.define
class Sett(SettingsBase):
    NUM: int = 0
    BOOL: bool = attrs.field(metadata=VAR_REQ, default=False)
    ROOT: Path = Path(".")


def test_types() -> None:
    """Types."""
    res = Sett()

    assert len(res._get_fields()) == 3

    res.load("A_")
    assert res.NUM == 5
    assert res.BOOL is True
    assert res.ROOT == Path(".")

    res.load("B_")
    assert res.NUM == 10
    assert res.BOOL is False
    assert res.ROOT == Path("/c/")

    with pytest.raises(ValueError):
        res.load("C_")
