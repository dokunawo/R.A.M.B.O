"""Pure-Python logistic regression — zero dependencies. Standardizes features on
the training set, fits L2-regularized log-loss by batch gradient descent, and
predicts a clamped probability. Knows nothing about baseball; just the math."""
from __future__ import annotations

import math


def _sigmoid(z: float) -> float:
    # overflow-safe logistic
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


class LogisticRegression:
    def __init__(self, l2: float = 0.0, lr: float = 0.1, epochs: int = 500,
                 feature_names: list[str] | None = None) -> None:
        self.l2 = l2
        self.lr = lr
        self.epochs = epochs
        self.feature_names = feature_names
        self.mean: list[float] = []
        self.std: list[float] = []
        self.w: list[float] = []
        self.b: float = 0.0

    def _standardize(self, x: list[float]) -> list[float]:
        return [(x[j] - self.mean[j]) / self.std[j] for j in range(len(x))]

    def fit(self, X: list[list[float]], y: list[int]) -> "LogisticRegression":
        if not X:
            return self
        n = len(X)
        d = len(X[0]) if n else 0
        # per-feature mean/std (population); zero variance -> std 1 (no-op scale)
        self.mean = [sum(row[j] for row in X) / n for j in range(d)]
        self.std = []
        for j in range(d):
            var = sum((row[j] - self.mean[j]) ** 2 for row in X) / n
            self.std.append(math.sqrt(var) if var > 1e-12 else 1.0)
        Xs = [self._standardize(row) for row in X]
        self.w = [0.0] * d
        self.b = 0.0
        for _ in range(self.epochs):
            gw = [0.0] * d
            gb = 0.0
            for i in range(n):
                p = _sigmoid(sum(self.w[j] * Xs[i][j] for j in range(d)) + self.b)
                err = p - y[i]
                for j in range(d):
                    gw[j] += err * Xs[i][j]
                gb += err
            for j in range(d):
                self.w[j] -= self.lr * (gw[j] / n + self.l2 * self.w[j])
            self.b -= self.lr * (gb / n)
        return self

    def predict_proba(self, x: list[float]) -> float:
        xs = self._standardize(x)
        z = sum(self.w[j] * xs[j] for j in range(len(xs))) + self.b
        return min(1.0 - 1e-6, max(1e-6, _sigmoid(z)))

    def coefficients(self) -> dict[str, float]:
        """Return fitted weights (intercept + per-feature). Weights are on the STANDARDIZED
        feature scale; magnitudes are not directly comparable to raw-feature units, but signs
        are meaningful for direction."""
        names = self.feature_names or [f"x{j}" for j in range(len(self.w))]
        out = {names[j]: self.w[j] for j in range(len(self.w))}
        out["intercept"] = self.b
        return out
