from __future__ import annotations

from typing import Optional

from ..models import EdgeRatio


def required_model_prob(market_prob: float, alpha: float, floor: float) -> float:
    """Mirror of btc_pricer/edge.py: required = max(floor, 1 - (1-p)^alpha)."""
    if market_prob is None:
        return floor
    market_prob = max(0.0, min(1.0, market_prob))
    return max(floor, 1.0 - (1.0 - market_prob) ** alpha)


def has_edge(model_prob: float, market_prob: float, alpha: float, floor: float) -> bool:
    return model_prob >= required_model_prob(market_prob, alpha, floor)


def _safe_ratio(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or den is None or den <= 0:
        return None
    return num / den


def compute_edge(
    side: str,
    model_prob: Optional[float],
    market_prob: Optional[float],
    alpha: float,
    floor: float,
) -> EdgeRatio:
    required = None
    current_ratio = None
    required_ratio = None
    margin = None
    has_e: Optional[bool] = None
    if market_prob is not None:
        required = required_model_prob(market_prob, alpha, floor)
        required_ratio = _safe_ratio(required, market_prob)
        if model_prob is not None:
            current_ratio = _safe_ratio(model_prob, market_prob)
            has_e = model_prob >= required
            if current_ratio is not None and required_ratio is not None:
                margin = current_ratio - required_ratio
    return EdgeRatio(
        side=side,  # type: ignore[arg-type]
        market_prob=market_prob,
        model_prob=model_prob,
        required_prob=required,
        current_ratio=current_ratio,
        required_ratio=required_ratio,
        margin=margin,
        has_edge=has_e,
    )
