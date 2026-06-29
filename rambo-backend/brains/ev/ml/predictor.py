"""Interchangeable moneyline predictors for the walk-forward harness. Both expose
prepare()/predict_home(); the harness only talks to this interface, so the closed-form
baseline and the learned model are graded identically."""
from __future__ import annotations

import datetime as _dt

from brains.ev.moneyline_model import evaluate_game_asof
from brains.ev.ml import features
from brains.ev.ml.logreg import LogisticRegression


class AnchoredPredictor:
    """The shipped closed-form market-anchored model, as a predictor (the baseline)."""

    def prepare(self, repo, season: int, before_date: str) -> None:
        return None

    def predict_home(self, repo, season: int, game: dict,
                     before_date: str) -> float | None:
        ev = evaluate_game_asof(repo, season, game, before_date)
        return ev["model_home"] if ev else None


class LogRegPredictor:
    """Learned logistic-regression model, refit on a weekly cadence (expanding
    window). Holds the fitted model + last-fit date as state."""

    def __init__(self, refit_days: int = 7, l2: float = 1.0, lr: float = 0.3,
                 epochs: int = 800) -> None:
        self.refit_days = refit_days
        self.l2 = l2
        self.lr = lr
        self.epochs = epochs
        self.model: LogisticRegression | None = None
        self.last_fit_date: str | None = None

    def _due(self, before_date: str) -> bool:
        if self.model is None or self.last_fit_date is None:
            return True
        d0 = _dt.date.fromisoformat(self.last_fit_date)
        d1 = _dt.date.fromisoformat(before_date)
        return (d1 - d0).days >= self.refit_days

    def prepare(self, repo, season: int, before_date: str) -> None:
        if not self._due(before_date):
            return
        X, y = features.training_set(repo, season, before_date)
        if not X:
            return
        self.model = LogisticRegression(
            l2=self.l2, lr=self.lr, epochs=self.epochs,
            feature_names=features.FEATURE_NAMES).fit(X, y)
        self.last_fit_date = before_date

    def predict_home(self, repo, season: int, game: dict,
                     before_date: str) -> float | None:
        if self.model is None:
            return None
        vec = features.game_feature_vector(repo, season, game, before_date)
        if vec is None:
            return None
        return self.model.predict_proba(vec)
