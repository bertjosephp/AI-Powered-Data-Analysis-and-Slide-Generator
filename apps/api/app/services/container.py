"""Builds the service graph once per app, choosing real or mock external clients."""

from dataclasses import dataclass

from fastapi import Request

from app.config import Settings
from app.pipeline.orchestrator import Pipeline
from app.services.gamma.client import GammaClient, GammaGenerator
from app.services.gamma.mock import MockGammaClient
from app.services.llm.analyst import ClaudeAnalyst, InsightsGenerator
from app.services.llm.client import make_anthropic_client
from app.services.llm.mock import MockAnalyst
from app.store.job_store import InMemoryJobStore, JobStore


@dataclass
class Services:
    store: JobStore
    pipeline: Pipeline
    gamma: GammaGenerator


def build_services(
    settings: Settings,
    analyst: InsightsGenerator | None = None,
    gamma: GammaGenerator | None = None,
) -> Services:
    if analyst is None:
        analyst = (
            MockAnalyst()
            if settings.mock_external
            else ClaudeAnalyst(make_anthropic_client(settings), settings.llm_model)
        )
    if gamma is None:
        gamma = (
            MockGammaClient()
            if settings.mock_external
            else GammaClient(
                settings.gamma_api_key,
                settings.gamma_base_url,
                settings.gamma_timeout_s,
                settings.gamma_poll_interval_s,
            )
        )
    store = InMemoryJobStore(settings.job_ttl_s)
    return Services(store=store, pipeline=Pipeline(store, analyst, gamma, settings), gamma=gamma)


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services
