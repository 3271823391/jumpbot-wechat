"""Empirical jump calibration. No coefficient exists before real measurements."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class JumpModel:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.samples = []
        if self.path.exists():
            self.samples = json.loads(self.path.read_text(encoding="utf-8"))

    def add(self, *, seconds: float, distance: float, direction: int,
            screen_width: int, confidence: float, source: str):
        if source != "real" or not 0.05 <= seconds <= 2 or distance <= 0:
            raise ValueError("模型只接受真实测量的有效跳跃")
        if not 0 < confidence <= 1 or direction not in (-1, 1):
            raise ValueError("无效的测量条件")
        self.samples.append(dict(seconds=seconds, distance=distance,
                                 direction=direction, screen_width=screen_width,
                                 confidence=confidence, source=source))
        self.path.parent.mkdir(exist_ok=True, parents=True)
        self.path.write_text(json.dumps(self.samples, ensure_ascii=False, indent=2), encoding="utf-8")

    def _xy(self, direction=None):
        rows = [s for s in self.samples if s["source"] == "real" and
                (direction is None or s["direction"] == direction)]
        x = np.array([s["seconds"] for s in rows], dtype=float)
        y = np.array([s["distance"] / s["screen_width"] for s in rows], dtype=float)
        w = np.array([s["confidence"] for s in rows], dtype=float)
        return x, y, w

    @staticmethod
    def _basis(x, kind):
        if kind == "linear":
            return np.column_stack([np.ones_like(x), x])
        if kind == "quadratic":
            return np.column_stack([np.ones_like(x), x, x*x])
        if kind == "sqrt":
            return np.column_stack([np.ones_like(x), np.sqrt(x)])
        raise ValueError(kind)

    @staticmethod
    def _robust_coeff(design, y, weights):
        robust = np.asarray(weights, dtype=float).copy()
        coefficients = None
        for _ in range(8):
            root = np.sqrt(robust)
            coefficients = np.linalg.lstsq(design * root[:, None], y * root, rcond=None)[0]
            residual = y - design @ coefficients
            scale = max(.003, 1.4826 * float(np.median(abs(residual))))
            limit = 1.5 * scale
            huber = np.minimum(1, limit / np.maximum(abs(residual), 1e-12))
            robust = weights * huber
        return coefficients

    def fit(self, direction=None):
        x, y, w = self._xy(direction)
        if len(x) < 8 or np.ptp(x) < .15 or len(np.unique(np.round(x, 2))) < 4:
            return None
        candidates = []
        for kind in ("linear", "quadratic", "sqrt"):
            errors = []
            for held in range(len(x)):
                mask = np.arange(len(x)) != held
                design = self._basis(x[mask], kind)
                coefficients = self._robust_coeff(design, y[mask], w[mask])
                errors.append(float((self._basis(x[held:held+1], kind) @ coefficients)[0] - y[held]))
            mae = float(np.mean(np.abs(errors)))
            coefficients = self._robust_coeff(self._basis(x, kind), y, w)
            # Reject non-monotonic fits over measured range.
            grid = np.linspace(x.min(), x.max(), 100)
            pred = self._basis(grid, kind) @ coefficients
            if np.any(np.diff(pred) <= 0):
                continue
            candidates.append((mae, kind, coefficients))
        if not candidates:
            return None
        best = min(candidates, key=lambda row: row[0])
        linear = next((row for row in candidates if row[1] == "linear"), None)
        mae, kind, coefficients = linear if linear and linear[0] <= best[0]*1.03 else best
        residual = y - self._basis(x, kind) @ coefficients
        return dict(kind=kind, coefficients=coefficients.tolist(),
                    loo_mae_normalized=mae, sample_count=len(x),
                    median_absolute_residual_normalized=float(np.median(abs(residual))),
                    seconds_range=[float(x.min()), float(x.max())])

    def predict_distance(self, seconds: float, width: int, direction=None):
        fit = self.fit(direction) or self.fit()
        if fit is None:
            return None
        if not fit["seconds_range"][0] <= seconds <= fit["seconds_range"][1]:
            return None
        normalized = float((self._basis(np.array([seconds]), fit["kind"]) @
                            np.array(fit["coefficients"]))[0])
        return dict(distance=normalized * width,
                    uncertainty=fit["loo_mae_normalized"] * width,
                    model=fit)

    def press_for(self, pixels: float, width: int, direction=None):
        fit = self.fit(direction) or self.fit()
        if fit is None:
            return None
        lo, hi = fit["seconds_range"]
        # Limited exploration outside the measured interval. Mark it so the
        # controller can apply a stricter uncertainty gate and record it.
        margin = min(.5, (hi-lo)*(.2 if fit["sample_count"] < 30 else .9))
        grid = np.linspace(max(.05, lo-margin), min(2.0, hi+margin), 400)
        predictions = self._basis(grid, fit["kind"]) @ np.array(fit["coefficients"])
        target = pixels / width
        if target < predictions.min() or target > predictions.max():
            return None
        index = int(np.argmin(abs(predictions - target)))
        extrapolated = bool(grid[index] < lo or grid[index] > hi)
        extent = max(lo-grid[index], grid[index]-hi, 0)
        uncertainty_factor = 1 + 3*extent/max(hi-lo, .05)
        return dict(seconds=float(grid[index]),
                    uncertainty_pixels=fit["loo_mae_normalized"] * width * uncertainty_factor,
                    extrapolated=extrapolated,
                    model=fit)
