"""Token usage and cost for one analysis, summed over every Claude call it made."""

from dataclasses import dataclass
from typing import Any

CACHE_READ_MULTIPLIER = 0.1  # of the input price
CACHE_WRITE_MULTIPLIER = 1.25  # 5-minute TTL writes


@dataclass
class Usage:
    input_tokens: int = 0  # uncached input only
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    calls: int = 0

    def add(self, usage: Any) -> None:
        """Accumulate an SDK `response.usage` object (missing fields count as 0)."""
        if usage is None:
            return
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.calls += 1

    def cost_usd(self, input_per_mtok: float, output_per_mtok: float) -> float:
        per_input = input_per_mtok / 1_000_000
        return (
            self.input_tokens * per_input
            + self.cache_read_tokens * per_input * CACHE_READ_MULTIPLIER
            + self.cache_write_tokens * per_input * CACHE_WRITE_MULTIPLIER
            + self.output_tokens * output_per_mtok / 1_000_000
        )
