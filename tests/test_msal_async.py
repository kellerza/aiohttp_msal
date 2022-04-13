from aiohttp_msal.msal_async import AsyncMSAL, Session


def test_ses():
    session = Session(None, new=True, data={"session": {"mail": "j@k", "name": "j"}})
    ses = AsyncMSAL(session)
    assert str(ses.name) == "j"
    assert str(ses.mail) == "j@k"
    assert str(ses.manager_mail) == ""
    assert str(ses.manager_name) == ""
