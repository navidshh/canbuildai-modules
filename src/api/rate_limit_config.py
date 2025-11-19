# config/rate_limits.py
from dataclasses import dataclass
from typing import Literal, Dict

Tier = Literal["Free-Tier", "Researcher-Tier", "Developer-Tier"]

@dataclass(frozen=True)
class RequestLimit:
    requests: int
    window_seconds: int

@dataclass(frozen=True)
class ConcurrencyLimit:
    max_concurrent: int

# Central, immutable configuration
REQUEST_LIMIT_CONFIG: Dict[Tier, RequestLimit] = {
    "Free-Tier":       RequestLimit(1,    300),   # 1 req / 10 min → 600 s 
    "Researcher-Tier": RequestLimit(1,    120),   # 1 req / 2 min
    "Developer-Tier":  RequestLimit(1000, 86400), # 1000 / day
}

CONCURRENCY_QUOTAS: Dict[Tier, ConcurrencyLimit] = {
    "Free-Tier":       ConcurrencyLimit(1),
    "Researcher-Tier": ConcurrencyLimit(1),
    "Developer-Tier":  ConcurrencyLimit(5),      # you can raise it later safely
}

# Optional helper (optional but very handy)
def get_limits(tier: Tier):
    return REQUEST_LIMIT_CONFIG[tier], CONCURRENCY_QUOTAS[tier]