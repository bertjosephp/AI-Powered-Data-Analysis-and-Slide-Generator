"""Builds the service graph once per app, choosing the real or mock analyst."""

from dataclasses import dataclass

from fastapi import Request

from app.config import Settings
from app.pipeline.orchestrator import Pipeline
from app.services.deck.pptx_renderer import DeckRenderer, PptxRenderer
from app.services.deck.theme import Theme
from app.services.llm.analyst import ClaudeAnalyst
from app.services.llm.client import make_anthropic_client
from app.services.llm.context import InsightsGenerator
from app.services.llm.mock import MockAnalyst
from app.store.artifact_store import ArtifactStore, InMemoryArtifactStore
from app.store.dataset_store import DatasetStore, InMemoryDatasetStore
from app.store.job_store import InMemoryJobStore, JobStore


@dataclass
class Services:
    store: JobStore
    artifacts: ArtifactStore
    datasets: DatasetStore
    pipeline: Pipeline


def build_services(
    settings: Settings,
    analyst: InsightsGenerator | None = None,
    renderer: DeckRenderer | None = None,
) -> Services:
    if analyst is None:
        analyst = (
            MockAnalyst()
            if settings.mock_external
            else ClaudeAnalyst(make_anthropic_client(settings), settings.llm_model)
        )
    renderer = renderer or PptxRenderer(Theme(font=settings.deck_font))
    store = InMemoryJobStore(settings.job_ttl_s)
    artifacts = InMemoryArtifactStore(settings.job_ttl_s)
    datasets = InMemoryDatasetStore(settings.job_ttl_s)
    return Services(
        store=store,
        artifacts=artifacts,
        datasets=datasets,
        pipeline=Pipeline(store, analyst, renderer, artifacts, datasets, settings),
    )


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services
