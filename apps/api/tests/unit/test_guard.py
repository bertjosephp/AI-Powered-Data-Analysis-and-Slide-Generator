from datetime import date
from types import SimpleNamespace

import pytest

from app.services.llm import guard as guard_module
from app.services.llm.guard import DemoGuard
from app.services.llm.usage import Usage


def test_admits_up_to_the_hourly_limit_per_visitor() -> None:
    guard = DemoGuard(runs_per_hour=2, daily_budget_usd=10, max_concurrent=10)
    assert guard.decide("a").use_claude and guard.decide("a").use_claude
    third = guard.decide("a")
    assert not third.use_claude and "2 Claude analyses per hour" in (third.note or "")
    assert guard.decide("b").use_claude  # limits are per visitor
    assert guard.remaining_for("a") == 0 and guard.remaining_for("b") == 1


def test_hourly_window_slides(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(guard_module.time, "monotonic", lambda: now[0])
    guard = DemoGuard(runs_per_hour=1, daily_budget_usd=10, max_concurrent=10)
    assert guard.decide("a").use_claude
    guard.finish(0)
    assert not guard.decide("a").use_claude
    now[0] += 3601
    assert guard.decide("a").use_claude


def test_daily_budget_caps_spend_and_resets(monkeypatch: pytest.MonkeyPatch) -> None:
    today = [date(2026, 9, 27)]
    monkeypatch.setattr(DemoGuard, "_today", staticmethod(lambda: today[0]))
    guard = DemoGuard(runs_per_hour=100, daily_budget_usd=0.5, max_concurrent=10)
    assert guard.decide("a").use_claude
    guard.finish(0.6)
    denied = guard.decide("b")
    assert not denied.use_claude and "daily Claude budget" in (denied.note or "")
    assert guard.status().budget_remaining_usd == 0
    today[0] = date(2026, 9, 28)
    assert guard.decide("b").use_claude


def test_concurrency_cap_and_release() -> None:
    guard = DemoGuard(runs_per_hour=100, daily_budget_usd=10, max_concurrent=1)
    assert guard.decide("a").use_claude
    busy = guard.decide("b")
    assert not busy.use_claude and "already running" in (busy.note or "")
    guard.finish(0.01)
    assert guard.decide("b").use_claude
    assert guard.status().spent_today_usd == pytest.approx(0.01)


def test_usage_accumulates_and_prices_cache_tokens() -> None:
    usage = Usage()
    usage.add(
        SimpleNamespace(
            input_tokens=1000,
            output_tokens=500,
            cache_read_input_tokens=10_000,
            cache_creation_input_tokens=2000,
        )
    )
    usage.add(
        SimpleNamespace(
            input_tokens=200,
            output_tokens=100,
            cache_read_input_tokens=None,
            cache_creation_input_tokens=0,
        )
    )
    usage.add(None)
    assert (usage.calls, usage.input_tokens, usage.output_tokens) == (2, 1200, 600)
    # $2/MTok in, $10/MTok out: 1200*2e-6 + 10000*2e-6*0.1 + 2000*2e-6*1.25 + 600*10e-6
    assert usage.cost_usd(2.0, 10.0) == pytest.approx(0.0024 + 0.002 + 0.005 + 0.006)
