"""Test settings."""

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import pytest

from aiohttp_msal.settings import ENV, VAR_REQ, SettingsBase


def test_load() -> None:
    """Load."""
    assert ENV.DOMAIN == ""

    with patch.dict(
        "os.environ",
        {
            "X_SP_APP_ID": "i1",
            "X_SP_APP_PW": "p1",
            "X_DOMAIN": "x.com",
            "X_SP_AUTHORITY": "a1",
        },
    ):
        ENV.load("X_")
        assert ENV.SP_APP_ID == "i1"
        assert ENV.SP_APP_PW == "p1"
        assert ENV.DOMAIN == "x.com"

    with patch.dict(
        "os.environ",
        {
            "Y_SP_APP_ID": "i2",
            "Y_SP_AUTHORITY": "a2",
            "Y_DOMAIN": "y.com",
            "Y_SP_APP_PW": "p2",
        },
    ):
        ENV.load("Y_")
    expected = {
        "Y_COOKIE_NAME": "AIOHTTP_SESSION",
        "Y_DOMAIN": "y.com",
        "Y_REDIS": "redis://redis1:6379",
        "Y_SP_APP_ID": "i2",
        "Y_SP_AUTHORITY": "a2",
    }
    assert ENV.asdict() == expected
    expected["Y_SP_APP_PW"] = "***"
    assert ENV.SP_AUTHORITY == "a2"
    assert ENV.asdict(hide="***") == expected


@dataclass
class Sett(SettingsBase):
    """Set."""

    NUM: int = 0
    BOOL: bool = field(metadata=VAR_REQ, default=False)
    ROOT: Path = Path()
    MAIN_URI: str = "http://example.com"


def test_types() -> None:
    """Types."""
    res = Sett()

    assert len(res.fields) == 4

    with patch.dict("os.environ", {"A_NUM": "5", "A_BOOL": "true", "A_ROOT": "/a"}):
        res.load("A_")
        assert res.NUM == 5
        assert res.BOOL is True
        assert res.ROOT == Path("/a")
        assert res.MAIN_URI == "http://example.com/"

    with patch.dict(
        "os.environ", {"B_NUM": "11", "B_BOOL": "false", "B_ROOT": "/c/d/"}
    ):
        res.load("B_")
        assert res.NUM == 11
        assert res.BOOL is False
        assert res.ROOT == Path("/c/d")

    with patch.dict("os.environ", {"MAIN_URI": "http://local/a", "BOOL": "1"}):
        res.load("")
        assert res.MAIN_URI == "http://local/a/"
        assert res.BOOL is True

    with pytest.raises(ValueError):
        with patch.dict("os.environ", {}):
            res.load("X_")


def test_db() -> None:
    """Test database settings."""
    assert not ENV.database
