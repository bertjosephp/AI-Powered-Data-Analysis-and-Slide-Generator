from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, anthropic_api_key="", gamma_api_key="", mock_external=True)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
