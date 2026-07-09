from __future__ import annotations

from app.models import Market


LIFECYCLE_MUTATION_STATES = {"trial", "active"}
LIFECYCLE_TRANSITIONS: dict[str, set[str]] = {
    "trial": {"active", "suspended", "archived"},
    "active": {"suspended", "archived"},
    "suspended": {"active", "archived"},
    "archived": set(),
}


def can_transition_lifecycle(current: str, target: str) -> bool:
    if current == target:
        return True
    return target in LIFECYCLE_TRANSITIONS.get(current, set())


def market_allows_mutations(market: Market | None) -> bool:
    return market is not None and market.is_active and market.lifecycle_status in LIFECYCLE_MUTATION_STATES


def inactive_market_message() -> str:
    return "Bu markette operasyonlar su anda aktif degil. Lutfen LeafletPilot ekibiyle iletisime gecin."
