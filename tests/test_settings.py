from aiohttp_msal.settings import ENV, Var


def test_load():
    assert ENV.DOMAIN == "mydomain.com"
    assert isinstance(ENV.SP_APP_ID, Var)
    ENV.load("X_")
    assert ENV.SP_APP_ID == "i1"
    assert ENV.SP_APP_PW == "p1"
    ENV.load()
    assert ENV.to_dict() == {"SP_APP_ID": "i2", "SP_APP_PW": "p2", "SP_AUTHORITY": "a2"}
