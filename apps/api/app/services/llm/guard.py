"""Protects a public demo's Claude budget.

Decides per upload whether the analysis runs on Claude or on the offline mock
analyst: a per-visitor hourly limit, a daily spending cap, and a cap on
concurrent Claude runs. When a limit is hit the job still runs, on the mock
analyst, with a note explaining why. In memory and per process, like the stores.
"""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, date, datetime


@dataclass(frozen=True)
class Decision:
    use_claude: bool
    note: str | None = None


@dataclass(frozen=True)
class GuardStatus:
    runs_per_hour: int
    daily_budget_usd: float
    spent_today_usd: float
    budget_remaining_usd: float
    active_runs: int


class DemoGuard:
    def __init__(
        self,
        runs_per_hour: int,
        daily_budget_usd: float,
        max_concurrent: int,
    ) -> None:
        self._runs_per_hour = runs_per_hour
        self._budget = daily_budget_usd
        self._max_concurrent = max_concurrent
        self._lock = threading.Lock()
        self._runs: dict[str, deque[float]] = defaultdict(deque)
        self._spent = 0.0
        self._spent_day = self._today()
        self._active = 0

    def decide(self, client_id: str) -> Decision:
        """Reserve a Claude run for this visitor, or explain why it will be mocked."""
        with self._lock:
            self._roll_day()
            now = time.monotonic()
            window = self._runs[client_id]
            while window and now - window[0] > 3600:
                window.popleft()
            if self._spent >= self._budget:
                return Decision(
                    False,
                    "The live demo's daily Claude budget is used up, so this run used the "
                    "offline analyst. It resets at midnight UTC.",
                )
            if len(window) >= self._runs_per_hour:
                return Decision(
                    False,
                    f"You've reached the demo limit of {self._runs_per_hour} Claude analyses "
                    "per hour, so this run used the offline analyst.",
                )
            if self._active >= self._max_concurrent:
                return Decision(
                    False,
                    "Several Claude analyses are already running, so this run used the "
                    "offline analyst. Try again in a minute.",
                )
            window.append(now)
            self._active += 1
            return Decision(True)

    def finish(self, cost_usd: float) -> None:
        """Release a reserved run and charge its actual cost."""
        with self._lock:
            self._roll_day()
            self._active = max(0, self._active - 1)
            self._spent += max(cost_usd, 0.0)

    def remaining_for(self, client_id: str) -> int:
        with self._lock:
            now = time.monotonic()
            window = self._runs[client_id]
            recent = sum(1 for t in window if now - t <= 3600)
            return max(self._runs_per_hour - recent, 0)

    def status(self) -> GuardStatus:
        with self._lock:
            self._roll_day()
            return GuardStatus(
                runs_per_hour=self._runs_per_hour,
                daily_budget_usd=self._budget,
                spent_today_usd=round(self._spent, 4),
                budget_remaining_usd=round(max(self._budget - self._spent, 0.0), 4),
                active_runs=self._active,
            )

    def _roll_day(self) -> None:
        today = self._today()
        if today != self._spent_day:
            self._spent_day, self._spent = today, 0.0

    @staticmethod
    def _today() -> date:
        return datetime.now(UTC).date()
