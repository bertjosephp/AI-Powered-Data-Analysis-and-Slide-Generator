from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services.container import build_services
from app.services.deck.pptx_renderer import DeckRenderer
from app.services.llm.context import InsightsGenerator
from app.services.llm.mock import MockAnalyst


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, anthropic_api_key="", mock_external=True)


def make_client(
    settings: Settings,
    analyst: InsightsGenerator | None = None,
    renderer: DeckRenderer | None = None,
    fallback: InsightsGenerator | None = None,
) -> TestClient:
    services = build_services(
        settings,
        analyst=analyst or MockAnalyst(latency_s=0),
        renderer=renderer,
        fallback=fallback,
    )
    app = create_app(settings, services)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with make_client(settings) as c:
        yield c
