"""Test the AsyncMSAL class."""

# from unittest.mock import patch

from aiohttp_msal.msal_async import AsyncMSAL, Session


def test_ses() -> None:
    """Test session."""
    session = Session(None, new=True, data={"session": {"mail": "j@k", "name": "j"}})
    ses = AsyncMSAL(session)
    assert str(ses.name) == "j"
    assert str(ses.mail) == "j@k"
    assert str(ses.manager_mail) == ""
    assert str(ses.manager_name) == ""


# async def test_request() -> None:
#     session = Session(None, new=True, data={"session": {"mail": "j@k", "name": "j"}})
#     ses = AsyncMSAL(session)
#     with patch.object(ses, "async_get_token") as mock_token:
#         mock_token.return_value = {"access_token": ""}

#         async with ses.request_ctx("get", "http://httpbin.org.get") as resp:
#             if resp.ok:
#                 return

#         async with ses.get("http://httpbin.org.get") as resp:
#             if resp.ok:
#                 return
