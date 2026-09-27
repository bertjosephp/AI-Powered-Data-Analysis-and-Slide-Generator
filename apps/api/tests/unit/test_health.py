from fastapi.testclient import TestClient

from app.config import Settings


def test_health_reports_ok_and_config(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json() == {
        "status": "ok",
        "anthropic_configured": False,
        "mock_external": True,
        "demo": None,  # no demo guard in mock mode
    }


def test_cors_origins_parse_comma_separated_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    assert Settings(_env_file=None).cors_origins == ["http://a.test", "http://b.test"]
