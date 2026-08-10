"""Deterministic, geometry-based flyer visual-quality scoring (Phase 28B).

Pure and DB-free except for `evaluate_layout_metrics_sync`, the single
function that talks to Playwright. Everything else here operates on plain
data so it is trivially unit-testable without a browser: construct a
`LayoutMetrics` by hand, call `score_from_metrics`, assert on `QualityScore`.

No OCR, no vision API - metrics come from DOM geometry
(`getBoundingClientRect`/computed styles), the same source already used by
the Playwright acceptance tests in `tests/test_flyer_visual_acceptance.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SCORE_ISSUE_THRESHOLD = 65.0

# Calibration anchors, chosen to line up with the pass floors already
# validated in tests/test_flyer_visual_acceptance.py (usedAreaRatio >= 0.68,
# reachesPageBottom at ~88%). Tunable; the qualitative behavior (what counts
# as "acceptable") is the fixed part.
_PAGE_FILL_FLOOR = 0.30
_PAGE_FILL_TARGET = 0.85
_WHITESPACE_PENALTY_SCALE = 230.0
# Card containers are laid out with height:100% by design (CSS grid rows
# share the available height evenly), so page_fill/whitespace - which both
# measure the *card container* box - read near-perfect even when a card's
# actual content (image/price/name) only fills a fraction of that box
# (Phase 31: confirmed root cause of the "large unused whitespace" production
# gap slipping past the gate). content_fill_score measures the worst-case
# card's real content bottom against its own container height instead.
_CONTENT_FILL_FLOOR = 0.35
_CONTENT_FILL_TARGET = 0.80
_CARD_BALANCE_BEST_RATIO = 1.0
_CARD_BALANCE_WORST_RATIO = 3.0
_HERO_AREA_FLOOR, _HERO_AREA_TARGET = 1.0, 2.5
_HERO_IMAGE_FLOOR, _HERO_IMAGE_TARGET = 1.0, 2.0
_HERO_PRICE_FLOOR, _HERO_PRICE_TARGET = 1.0, 1.4
_PRICE_WIDTH_FLOOR, _PRICE_WIDTH_TARGET = 0.15, 0.5
_IMAGE_COVERAGE_FLOOR, _IMAGE_COVERAGE_TARGET = 0.10, 0.45
_IMAGE_FALLBACK_SCORE = 60.0
_IMAGE_UNKNOWN_SCORE = 70.0
_PRICE_CLIPPED_SCORE_CAP = 20.0

_BASE_WEIGHTS = {
    "page_fill_score": 0.12,
    "whitespace_score": 0.12,
    "content_fill_score": 0.14,
    "card_balance_score": 0.12,
    "hero_dominance_score": 0.14,
    "price_legibility_score": 0.14,
    "image_coverage_score": 0.08,
    "collision_score": 0.09,
    "overflow_score": 0.05,
}

# A layout can average out to a passing weighted score while one truly
# critical dimension has collapsed (e.g. severe under-fill masked by perfect
# collision/overflow scores - the exact Phase 31 production gap). These
# dimensions answer "did the layout actually work", as opposed to the softer
# aesthetic dimensions (card_balance, hero_dominance, image_coverage); if any
# of them falls below the floor, cap the overall score below QUALITY_THRESHOLD
# (72.0 in visual_quality_gate.py) regardless of how well the others scored.
_CRITICAL_DIMENSIONS = ("page_fill_score", "whitespace_score", "content_fill_score", "price_legibility_score")
_CRITICAL_FLOOR = 20.0
_CRITICAL_VETO_CAP = 55.0

_METRICS_JS = """() => {
  const rect = (el) => { const r = el.getBoundingClientRect(); return {left: r.left, top: r.top, right: r.right, bottom: r.bottom}; };
  const area = (box) => Math.max(0, box.right - box.left) * Math.max(0, box.bottom - box.top);
  const overlaps = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
  const doc = document.querySelector('.preview-document');
  const docBox = rect(doc);
  const grid = document.querySelector('.product-grid');
  const gridBox = rect(grid);
  const footer = document.querySelector('.footer');
  const cards = [...document.querySelectorAll('.product-card')];
  const cardBoxes = cards.map(rect);
  const stages = cards.map((c) => c.querySelector('.promo-card-image'));
  const panels = cards.map((c) => c.querySelector('.price-panel'));
  const prices = cards.map((c) => c.querySelector('.price'));
  const names = cards.map((c) => c.querySelector('.product-name'));

  const featuredIndex = cards.findIndex((c) => c.dataset.merchandisingRole === 'featured' || c.dataset.emphasis === 'featured');
  const hasFeatured = featuredIndex >= 0;
  const supportIndexes = cards.map((_, i) => i).filter((i) => i !== featuredIndex);

  const totalCardArea = cardBoxes.reduce((sum, box) => sum + area(box), 0);
  const gridArea = area(gridBox);
  const gridHeight = Math.max(1, gridBox.bottom - gridBox.top);
  const maxBottom = cardBoxes.length ? Math.max(...cardBoxes.map((b) => b.bottom)) : gridBox.top;
  const bottomGapRatio = Math.max(0, (gridBox.bottom - maxBottom) / gridHeight);

  const nonFeaturedAreas = supportIndexes.map((i) => area(cardBoxes[i]));

  const priceWidthRatios = cards.map((card, i) => {
    const panel = panels[i];
    if (!panel) return null;
    const cardBox = cardBoxes[i];
    const cardWidth = cardBox.right - cardBox.left;
    if (cardWidth <= 0) return null;
    const panelBox = rect(panel);
    return (panelBox.right - panelBox.left) / cardWidth;
  }).filter((v) => v !== null);

  const priceClipped = prices.some((price) => price && price.scrollWidth > price.clientWidth + 1);

  const imageAreaRatios = cards.map((card, i) => {
    if (card.dataset.imageAvailable !== 'true') return null;
    const stage = stages[i];
    if (!stage) return null;
    const cardArea = area(cardBoxes[i]);
    if (cardArea <= 0) return null;
    return area(rect(stage)) / cardArea;
  }).filter((v) => v !== null);

  const fallbackCount = document.querySelectorAll('.image-placeholder').length;

  const cardContentFillRatios = cards.map((card, i) => {
    const box = cardBoxes[i];
    const cardHeight = box.bottom - box.top;
    if (cardHeight <= 0) return null;
    const contentEls = [stages[i], panels[i], card.querySelector('.brand-label'), names[i], card.querySelector('.product-unit')].filter(Boolean);
    if (!contentEls.length) return null;
    const contentBottom = Math.max(...contentEls.map((el) => rect(el).bottom));
    return Math.max(0, Math.min(1, (contentBottom - box.top) / cardHeight));
  }).filter((v) => v !== null);

  const noStageTextCollision = cards.every((card, i) => {
    const stage = stages[i], name = names[i], panel = panels[i];
    if (!stage || !name || !panel) return true;
    const s = rect(stage), n = rect(name), p = rect(panel);
    return !overlaps(s, n) && !overlaps(s, p) && !overlaps(n, p);
  });
  const badgesInside = [...document.querySelectorAll('.promo-badge')].every((badge) => {
    const badgeBox = rect(badge);
    const cardBox = rect(badge.closest('.product-card'));
    return badgeBox.left >= cardBox.left - 1 && badgeBox.right <= cardBox.right + 1 && badgeBox.top >= cardBox.top - 1 && badgeBox.bottom <= cardBox.bottom + 1;
  });
  const pricesInside = prices.every((price, i) => {
    if (!price) return true;
    const panel = panels[i];
    if (!panel) return true;
    const priceBox = rect(price), panelBox = rect(panel);
    return priceBox.left >= panelBox.left - 1 && priceBox.right <= panelBox.right + 1 && priceBox.top >= panelBox.top - 1 && priceBox.bottom <= panelBox.bottom + 1;
  });
  const footerAfterGrid = !footer || rect(footer).top >= gridBox.bottom - 1;
  const cardsInside = footerAfterGrid && cardBoxes.every((box) => box.left >= docBox.left - 1 && box.top >= docBox.top - 1 && box.right <= docBox.right + 1 && box.bottom <= docBox.bottom + 1);
  const gridInside = gridBox.left >= docBox.left - 1 && gridBox.right <= docBox.right + 1 && gridBox.bottom <= docBox.bottom + 1;
  const noCardOverflow = cards.every((card) => card.scrollWidth <= card.clientWidth + 1 && card.scrollHeight <= card.clientHeight + 1);
  const noCollisions = cardBoxes.every((box, i) => cardBoxes.slice(i + 1).every((other) => !overlaps(box, other)));

  const featuredStage = hasFeatured ? stages[featuredIndex] : null;
  const featuredPrice = hasFeatured ? prices[featuredIndex] : null;
  const supportImageAreas = supportIndexes.map((i) => (stages[i] ? area(rect(stages[i])) : null)).filter((v) => v !== null);
  const supportPriceSizes = supportIndexes.map((i) => (prices[i] ? parseFloat(getComputedStyle(prices[i]).fontSize) : null)).filter((v) => v !== null);

  return {
    viewportWidth: document.documentElement.scrollWidth,
    viewportHeight: document.documentElement.scrollHeight,
    cardCount: cards.length,
    cardsInside, gridInside, noCardOverflow, noCollisions, noStageTextCollision, badgesInside, pricesInside,
    gridArea, totalCardArea, bottomGapRatio, nonFeaturedAreas,
    hasFeatured,
    featuredArea: hasFeatured ? area(cardBoxes[featuredIndex]) : null,
    maxSupportArea: nonFeaturedAreas.length ? Math.max(...nonFeaturedAreas) : null,
    featuredImageArea: featuredStage ? area(rect(featuredStage)) : null,
    maxSupportImageArea: supportImageAreas.length ? Math.max(...supportImageAreas) : null,
    featuredPriceSize: featuredPrice ? parseFloat(getComputedStyle(featuredPrice).fontSize) : null,
    maxSupportPriceSize: supportPriceSizes.length ? Math.max(...supportPriceSizes) : null,
    priceWidthRatios, priceClipped, imageAreaRatios, fallbackCount, cardContentFillRatios,
  };
}"""


@dataclass(frozen=True)
class LayoutMetrics:
    """Raw geometry facts read from the rendered DOM. No scoring logic here."""

    viewport_width: float
    viewport_height: float
    card_count: int
    cards_inside: bool
    grid_inside: bool
    no_card_overflow: bool
    no_collisions: bool
    no_stage_text_collision: bool
    badges_inside: bool
    prices_inside: bool
    grid_area: float
    total_card_area: float
    bottom_gap_ratio: float
    non_featured_card_areas: list[float] = field(default_factory=list)
    has_featured: bool = False
    featured_area: float | None = None
    max_support_area: float | None = None
    featured_image_area: float | None = None
    max_support_image_area: float | None = None
    featured_price_size: float | None = None
    max_support_price_size: float | None = None
    price_width_ratios: list[float] = field(default_factory=list)
    price_clipped: bool = False
    image_area_ratios: list[float] = field(default_factory=list)
    fallback_count: int = 0
    card_content_fill_ratios: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class ScoreContext:
    """Non-geometric facts scoring needs to interpret metrics correctly."""

    item_count: int
    has_explicit_hero: bool
    layout_name: str
    visual_mode: str


@dataclass(frozen=True)
class QualityScore:
    overall_score: float
    page_fill_score: float
    whitespace_score: float
    content_fill_score: float
    card_balance_score: float
    hero_dominance_score: float
    hero_dominance_applicable: bool
    price_legibility_score: float
    image_coverage_score: float
    collision_score: float
    overflow_score: float
    issues: tuple[str, ...] = ()

    @property
    def overflow_ok(self) -> bool:
        return self.overflow_score >= 100.0

    @property
    def collision_ok(self) -> bool:
        return self.collision_score >= 100.0


def evaluate_layout_metrics_sync(page: object) -> LayoutMetrics:
    """Read one Playwright Page (already `set_content`) into `LayoutMetrics`.

    Browser/page lifecycle is owned by the caller (see visual_quality_gate.py),
    not here - this function only runs the one JS evaluate call.
    """
    raw = page.evaluate(_METRICS_JS)  # type: ignore[attr-defined]
    return LayoutMetrics(
        viewport_width=raw["viewportWidth"],
        viewport_height=raw["viewportHeight"],
        card_count=raw["cardCount"],
        cards_inside=raw["cardsInside"],
        grid_inside=raw["gridInside"],
        no_card_overflow=raw["noCardOverflow"],
        no_collisions=raw["noCollisions"],
        no_stage_text_collision=raw["noStageTextCollision"],
        badges_inside=raw["badgesInside"],
        prices_inside=raw["pricesInside"],
        grid_area=raw["gridArea"],
        total_card_area=raw["totalCardArea"],
        bottom_gap_ratio=raw["bottomGapRatio"],
        non_featured_card_areas=list(raw["nonFeaturedAreas"]),
        has_featured=raw["hasFeatured"],
        featured_area=raw["featuredArea"],
        max_support_area=raw["maxSupportArea"],
        featured_image_area=raw["featuredImageArea"],
        max_support_image_area=raw["maxSupportImageArea"],
        featured_price_size=raw["featuredPriceSize"],
        max_support_price_size=raw["maxSupportPriceSize"],
        price_width_ratios=list(raw["priceWidthRatios"]),
        price_clipped=raw["priceClipped"],
        image_area_ratios=list(raw["imageAreaRatios"]),
        fallback_count=raw["fallbackCount"],
        card_content_fill_ratios=list(raw["cardContentFillRatios"]),
    )


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _linear_score(value: float, floor: float, target: float) -> float:
    if target == floor:
        return 100.0 if value >= target else 0.0
    return _clamp((value - floor) / (target - floor) * 100.0)


def _page_fill_score(metrics: LayoutMetrics) -> float:
    if metrics.grid_area <= 0:
        return 0.0
    used_ratio = metrics.total_card_area / metrics.grid_area
    return _linear_score(used_ratio, _PAGE_FILL_FLOOR, _PAGE_FILL_TARGET)


def _whitespace_score(metrics: LayoutMetrics) -> float:
    return _clamp(100.0 - metrics.bottom_gap_ratio * _WHITESPACE_PENALTY_SCALE)


def _content_fill_score(metrics: LayoutMetrics) -> float:
    if not metrics.card_content_fill_ratios:
        return 100.0
    worst_ratio = min(metrics.card_content_fill_ratios)
    return _linear_score(worst_ratio, _CONTENT_FILL_FLOOR, _CONTENT_FILL_TARGET)


def _card_balance_score(metrics: LayoutMetrics) -> float:
    areas = [a for a in metrics.non_featured_card_areas if a > 0]
    if len(areas) < 2:
        return 100.0
    ratio = max(areas) / min(areas)
    return _linear_score(-ratio, -_CARD_BALANCE_WORST_RATIO, -_CARD_BALANCE_BEST_RATIO)


def _hero_dominance(metrics: LayoutMetrics, context: ScoreContext) -> tuple[float, bool]:
    if not context.has_explicit_hero or not metrics.has_featured:
        return 100.0, False
    sub_scores: list[float] = []
    if metrics.featured_area and metrics.max_support_area:
        sub_scores.append(_linear_score(metrics.featured_area / metrics.max_support_area, _HERO_AREA_FLOOR, _HERO_AREA_TARGET))
    if metrics.featured_image_area and metrics.max_support_image_area:
        sub_scores.append(_linear_score(metrics.featured_image_area / metrics.max_support_image_area, _HERO_IMAGE_FLOOR, _HERO_IMAGE_TARGET))
    if metrics.featured_price_size and metrics.max_support_price_size:
        sub_scores.append(_linear_score(metrics.featured_price_size / metrics.max_support_price_size, _HERO_PRICE_FLOOR, _HERO_PRICE_TARGET))
    if not sub_scores:
        return 100.0, False
    return sum(sub_scores) / len(sub_scores), True


def _price_legibility_score(metrics: LayoutMetrics) -> float:
    if not metrics.price_width_ratios:
        score = 100.0
    else:
        score = sum(_linear_score(ratio, _PRICE_WIDTH_FLOOR, _PRICE_WIDTH_TARGET) for ratio in metrics.price_width_ratios) / len(metrics.price_width_ratios)
    if metrics.price_clipped:
        score = min(score, _PRICE_CLIPPED_SCORE_CAP)
    return score


def _image_coverage_score(metrics: LayoutMetrics) -> float:
    if metrics.card_count <= 0:
        return 100.0
    real_scores = [_linear_score(ratio, _IMAGE_COVERAGE_FLOOR, _IMAGE_COVERAGE_TARGET) for ratio in metrics.image_area_ratios]
    fallback_scores = [_IMAGE_FALLBACK_SCORE] * metrics.fallback_count
    accounted = len(real_scores) + len(fallback_scores)
    unknown_scores = [_IMAGE_UNKNOWN_SCORE] * max(0, metrics.card_count - accounted)
    per_card = real_scores + fallback_scores + unknown_scores
    return sum(per_card) / len(per_card) if per_card else 100.0


def score_from_metrics(metrics: LayoutMetrics, *, context: ScoreContext) -> QualityScore:
    """Pure: derive the 8 named quality scores + issues from raw geometry."""
    overflow_ok = metrics.cards_inside and metrics.grid_inside and metrics.no_card_overflow
    collision_ok = metrics.no_collisions and metrics.no_stage_text_collision and metrics.badges_inside and metrics.prices_inside

    page_fill_score = _page_fill_score(metrics)
    whitespace_score = _whitespace_score(metrics)
    content_fill_score = _content_fill_score(metrics)
    card_balance_score = _card_balance_score(metrics)
    hero_dominance_score, hero_applicable = _hero_dominance(metrics, context)
    price_legibility_score = _price_legibility_score(metrics)
    image_coverage_score = _image_coverage_score(metrics)
    collision_score = 100.0 if collision_ok else 0.0
    overflow_score = 100.0 if overflow_ok else 0.0

    scores = {
        "page_fill_score": page_fill_score,
        "whitespace_score": whitespace_score,
        "content_fill_score": content_fill_score,
        "card_balance_score": card_balance_score,
        "price_legibility_score": price_legibility_score,
        "image_coverage_score": image_coverage_score,
        "collision_score": collision_score,
        "overflow_score": overflow_score,
    }
    weights = dict(_BASE_WEIGHTS)
    if hero_applicable:
        scores["hero_dominance_score"] = hero_dominance_score
    else:
        redistribute = weights.pop("hero_dominance_score")
        remaining_total = sum(weights.values())
        weights = {key: value + redistribute * (value / remaining_total) for key, value in weights.items()}
    total_weight = sum(weights[key] for key in scores)
    overall_score = sum(scores[key] * weights[key] for key in scores) / total_weight if total_weight else 0.0

    issues: list[str] = []
    if page_fill_score < SCORE_ISSUE_THRESHOLD:
        issues.append("page_fill_low")
    if whitespace_score < SCORE_ISSUE_THRESHOLD:
        issues.append("whitespace_excessive")
    if content_fill_score < SCORE_ISSUE_THRESHOLD:
        issues.append("content_fill_low")
    if card_balance_score < SCORE_ISSUE_THRESHOLD:
        issues.append("card_balance_uneven")
    if hero_applicable and hero_dominance_score < SCORE_ISSUE_THRESHOLD:
        issues.append("hero_dominance_weak")
    if price_legibility_score < SCORE_ISSUE_THRESHOLD:
        issues.append("price_legibility_low")
    if metrics.price_clipped:
        issues.append("price_text_clipped")
    if image_coverage_score < SCORE_ISSUE_THRESHOLD:
        issues.append("image_coverage_low")
    if metrics.fallback_count > 0:
        issues.append("image_fallback_present")
    if not collision_ok:
        issues.append("collision_detected")
    if not overflow_ok:
        issues.append("overflow_detected")

    critical_min = min(scores[key] for key in _CRITICAL_DIMENSIONS)
    if critical_min < _CRITICAL_FLOOR:
        overall_score = min(overall_score, _CRITICAL_VETO_CAP)
        issues.append("critical_dimension_floor_veto")

    return QualityScore(
        overall_score=overall_score,
        page_fill_score=page_fill_score,
        whitespace_score=whitespace_score,
        content_fill_score=content_fill_score,
        card_balance_score=card_balance_score,
        hero_dominance_score=hero_dominance_score,
        hero_dominance_applicable=hero_applicable,
        price_legibility_score=price_legibility_score,
        image_coverage_score=image_coverage_score,
        collision_score=collision_score,
        overflow_score=overflow_score,
        issues=tuple(issues),
    )
