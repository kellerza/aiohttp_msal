"""Init."""

from unittest.mock import MagicMock, patch

import pytest

import aiohttp_msal.routes  # noqa
from aiohttp_msal import auth_ok, msal_session


def a_yes(ses):
    return True


def a_no(ses):
    return False


@msal_session(a_yes, a_yes)
async def t_2yes(request, ses):
    return True


@msal_session(a_no, a_yes, at_least_one=True)
async def t_1no1yes_one(request, ses):
    return True


@msal_session(a_no, a_no, at_least_one=True)
async def t_2no_one(request, ses):
    return True


@patch("aiohttp_msal.get_session")
async def test_include_any(get_session: MagicMock):
    get_session.return_value = {}

    assert await t_2yes({})

    with pytest.raises(Exception):
        await t_1no1yes_one

    with pytest.raises(Exception):
        await t_2no_one


async def func(request, ses):
    return True


@patch("aiohttp_msal.get_session")
async def test_msal_session_auth(get_session: MagicMock):
    get_session.return_value = {}

    assert await msal_session(a_yes, a_yes)(func)({})
    assert await msal_session(a_yes, a_no, at_least_one=True)(func)({})
    assert await msal_session(a_no, a_yes, at_least_one=True)(func)({})
    assert await msal_session(a_no, a_no, a_no, a_yes, at_least_one=True)(func)({})

    with pytest.raises(Exception):
        await msal_session(a_yes, a_no)(func)({})

    with pytest.raises(Exception):
        await msal_session(a_yes, a_yes, a_no)(func)({})

    with pytest.raises(Exception):
        await msal_session(a_no, a_no, at_least_one=True)(func)({})


@patch("aiohttp_msal.get_session")
async def test_auth_ok(get_session: MagicMock):
    get_session.return_value = {"mail": "yes!"}

    assert await msal_session(a_yes)(func)({})

    get_session.return_value = {}

    with pytest.raises(Exception):
        assert await msal_session(a_yes, auth_ok)(func)({})
