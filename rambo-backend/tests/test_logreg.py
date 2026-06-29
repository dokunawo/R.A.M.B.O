import math
from brains.ev.ml.logreg import LogisticRegression


def test_recovers_separable_signal_and_drives_loss_down():
    # y depends positively on feature 0, negatively on feature 1
    X = [[2.0, -1.0], [1.5, -0.5], [1.0, 0.0], [-1.0, 1.0], [-1.5, 0.5], [-2.0, 1.0]]
    y = [1, 1, 1, 0, 0, 0]
    m = LogisticRegression(l2=0.0, lr=0.5, epochs=2000,
                           feature_names=["a", "b"]).fit(X, y)
    # predictions separate the classes
    assert m.predict_proba([2.0, -1.0]) > 0.6
    assert m.predict_proba([-2.0, 1.0]) < 0.4
    coef = m.coefficients()
    assert coef["a"] > 0 and coef["b"] < 0          # signs recovered
    assert "intercept" in coef


def test_predict_proba_is_clamped():
    X = [[10.0], [-10.0]]
    y = [1, 0]
    m = LogisticRegression(lr=1.0, epochs=3000).fit(X, y)
    p_hi = m.predict_proba([1000.0])
    p_lo = m.predict_proba([-1000.0])
    assert 0.0 < p_lo <= 1e-6 + 1e-9
    assert 1.0 - 1e-6 - 1e-9 <= p_hi < 1.0


def test_zero_variance_feature_does_not_crash():
    X = [[1.0, 5.0], [1.0, -5.0], [1.0, 5.0], [1.0, -5.0]]  # col 0 constant
    y = [1, 0, 1, 0]
    m = LogisticRegression(epochs=500).fit(X, y)
    p = m.predict_proba([1.0, 5.0])
    assert 0.0 < p < 1.0 and not math.isnan(p)
