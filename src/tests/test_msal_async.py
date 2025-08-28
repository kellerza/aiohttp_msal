"""Test the AsyncMSAL class."""

from aiohttp_msal.msal_async import AsyncMSAL, Session


def test_ses() -> None:
    """Test session."""
    session = Session(None, new=True, data={"session": {"mail": "j@k", "name": "j"}})
    ses = AsyncMSAL(session)
    assert ses.name == "j"
    assert ses.mail == "j@k"
    assert ses.manager_mail == ""
    assert ses.manager_name == ""

    assert ses.session["name"] == "j"
    assert ses.name == "j"
    ses.name = ""
    assert "name" not in ses.session
    assert ses.name == ""


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
