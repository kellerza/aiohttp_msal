"""Init."""

from unittest.mock import MagicMock, patch

import pytest

import aiohttp_msal.routes  # noqa
from aiohttp_msal import auth_ok, msal_session
from aiohttp_msal.msal_async import AsyncMSAL


def a_yes(ses: AsyncMSAL) -> bool:
    return True


def a_no(ses: AsyncMSAL) -> bool:
    return False


@msal_session(a_yes, a_yes)
async def t_2yes(request: dict, ses: AsyncMSAL) -> bool:
    return True


@msal_session(a_no, a_yes, at_least_one=True)
async def t_1no1yes_ok(request: dict, ses: AsyncMSAL) -> bool:
    return True


@msal_session(a_no, a_yes, at_least_one=False)
async def t_1no1yes_nok(request: dict, ses: AsyncMSAL) -> bool:
    return True


@msal_session(a_no, a_no, at_least_one=True)
async def t_2no_nok(request: dict, ses: AsyncMSAL) -> bool:
    return True


@msal_session(a_no, a_no, at_least_one=False)
async def t_2noa_nok(request: dict, ses: AsyncMSAL) -> bool:
    return True


@patch("aiohttp_msal.get_session")
async def test_include_any(get_session: MagicMock) -> None:
    get_session.return_value = {}

    for func in [t_2yes, t_1no1yes_ok]:
        assert await func({}) is True
    assert get_session.call_count == 2

    for func in [t_1no1yes_nok, t_2no_nok, t_2noa_nok]:
        with pytest.raises(Exception) as err:
            assert await func({}) is True
        assert "Forbidden" in str(err)
    assert get_session.call_count == 5


async def func(request: dict, ses: AsyncMSAL) -> bool:
    return True


@patch("aiohttp_msal.get_session")
async def test_msal_session_auth(get_session: MagicMock) -> None:
    get_session.return_value = {}

    assert await msal_session(a_yes, a_yes)(func)({})
    assert await msal_session(a_yes, a_no, at_least_one=True)(func)({})
    assert await msal_session(a_no, a_yes, at_least_one=True)(func)({})
    assert await msal_session(a_no, a_no, a_no, a_yes, at_least_one=True)(func)({})
    assert get_session.call_count == 4

    with pytest.raises(Exception):
        await msal_session(a_yes, a_no)(func)({})

    with pytest.raises(Exception):
        await msal_session(a_yes, a_yes, a_no)(func)({})

    with pytest.raises(Exception):
        await msal_session(a_no, a_no, at_least_one=True)(func)({})
    assert get_session.call_count == 7


@patch("aiohttp_msal.get_session")
async def test_auth_ok(get_session: MagicMock) -> None:
    get_session.return_value = {"mail": "yes!"}

    assert await msal_session(a_yes)(func)({})

    get_session.return_value = {}

    with pytest.raises(Exception):
        assert await msal_session(a_yes, auth_ok)(func)({})
