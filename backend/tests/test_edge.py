from app.derive.edge import required_model_prob, has_edge, compute_edge


def test_required_floor_applies():
    # Low market prob should be capped at the floor
    assert required_model_prob(0.05, alpha=1.0, floor=0.55) == 0.55


def test_required_uses_alpha_above_floor():
    # market=0.80, alpha=2 → 1 - 0.2^2 = 0.96
    r = required_model_prob(0.80, alpha=2.0, floor=0.5)
    assert abs(r - 0.96) < 1e-9


def test_has_edge_true_and_false():
    assert has_edge(model_prob=0.97, market_prob=0.80, alpha=2.0, floor=0.5) is True
    assert has_edge(model_prob=0.94, market_prob=0.80, alpha=2.0, floor=0.5) is False


def test_compute_edge_fields():
    e = compute_edge("UP", model_prob=0.7, market_prob=0.5, alpha=1.5, floor=0.55)
    assert e.side == "UP"
    assert e.market_prob == 0.5
    assert e.model_prob == 0.7
    assert e.required_prob is not None
    assert e.current_ratio is not None
    assert e.required_ratio is not None
    assert e.margin is not None
    assert e.has_edge is (e.model_prob >= e.required_prob)


def test_compute_edge_missing_market():
    e = compute_edge("DOWN", model_prob=0.7, market_prob=None, alpha=1.5, floor=0.55)
    assert e.required_prob is None
    assert e.has_edge is None
    assert e.current_ratio is None
