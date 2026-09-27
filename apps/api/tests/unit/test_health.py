from fastapi.testclient import TestClient

from app.config import Settings


def test_health_reports_ok_and_config(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json() == {
        "status": "ok",
        "anthropic_configured": False,
        "mock_external": True,
        "commit": None,
        "demo": None,  # no demo guard in mock mode
    }


def test_commit_comes_from_render_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    assert Settings(_env_file=None).git_commit == "abc123"


def test_cors_origins_parse_comma_separated_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    assert Settings(_env_file=None).cors_origins == ["http://a.test", "http://b.test"]


def test_cors_origin_regex_allows_preview_urls() -> None:
    from app.main import create_app

    settings = Settings(
        _env_file=None,
        mock_external=True,
        cors_origins=["https://prod.test"],
        cors_origin_regex=r"https://data-to-deck-[a-z0-9-]+\.vercel\.app",
    )
    with TestClient(create_app(settings)) as c:
        ok = c.get("/api/v1/health", headers={"Origin": "https://data-to-deck-git-pr-3.vercel.app"})
        bad = c.get("/api/v1/health", headers={"Origin": "https://evil.test"})
    assert (
        ok.headers.get("access-control-allow-origin") == "https://data-to-deck-git-pr-3.vercel.app"
    )
    assert "access-control-allow-origin" not in bad.headers
