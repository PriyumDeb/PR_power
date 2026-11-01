from src import __version__


def test_package_metadata():
    assert __version__ == "0.1.0"


def test_web_cockpit_endpoint():
    from starlette.testclient import TestClient
    from src.web import app
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    assert "ClaimCheck" in res.text
