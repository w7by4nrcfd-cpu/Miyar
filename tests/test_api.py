from fastapi.testclient import TestClient

from miyar import __version__
from miyar.api import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "miyar", "version": __version__}


def test_only_health_is_exposed():
    # هيكل فقط: لا نقاط أخرى (ولا صفحات توثيق تلقائية)
    paths = {route.path for route in app.routes}
    assert paths == {"/health"}
    assert client.get("/docs").status_code == 404
