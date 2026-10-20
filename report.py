"""Generate audit reports from actual event records; missing values remain missing."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from model import JumpModel
from jumpbot import score_change

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def main():
    events_path = DATA / "events.jsonl"
    events = []
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    trials = [e for e in events if "actual_press_seconds" in e]
    measured = [e for e in trials if e.get("valid_measurement") and e.get("measurement")]
    successes = sum(bool(e["measurement"].get("success_estimate")) for e in measured)
    score_confirmed_unmeasured = set()
    for e in trials:
        if e.get("valid_measurement"):
            continue
        before_path = e.get("before_capture") or e.get("capture")
        after_path = e.get("after_capture")
        if before_path and after_path and Path(before_path).exists() and Path(after_path).exists():
            with Image.open(before_path) as before, Image.open(after_path) as after:
                if score_change(before, after)[0] >= 80:
                    score_confirmed_unmeasured.add(e["time"])
    score_confirmed_successes = successes + len(score_confirmed_unmeasured)
    rounds_file = DATA / "rounds.json"
    rounds = json.loads(rounds_file.read_text(encoding="utf-8")) if rounds_file.exists() else []
    live_scores_file = DATA / "live_score_observations.json"
    live_scores = (json.loads(live_scores_file.read_text(encoding="utf-8"))
                   if live_scores_file.exists() else [])
    boundaries_file = DATA / "session_boundaries.json"
    boundaries = (json.loads(boundaries_file.read_text(encoding="utf-8"))
                  if boundaries_file.exists() else [])
    boundary_times = {b["first_trial_time"] for b in boundaries}
    simulation_file = DATA / "simulation_summary.json"
    simulation = json.loads(simulation_file.read_text(encoding="utf-8")) if simulation_file.exists() else None
    streak, longest = 0, 0
    round_attempts = []
    current_attempts = 0
    for trial in trials:
        if trial["time"] in boundary_times:
            streak, current_attempts = 0, 0
        current_attempts += 1
        if ((trial.get("valid_measurement") and
             trial.get("measurement", {}).get("success_estimate")) or
                trial["time"] in score_confirmed_unmeasured):
            streak += 1
            longest = max(longest, streak)
        else:
            round_attempts.append(current_attempts)
            current_attempts, streak = 0, 0
    model = JumpModel(DATA / "model.json")
    fit = model.fit()
    x, y, w = model._xy()
    comparison = {}
    chronological_holdout = {}
    if len(x) >= 8:
        width = int(np.median([s["screen_width"] for s in model.samples]))
        for kind in ("linear", "quadratic", "sqrt"):
            errors = []
            for held in range(len(x)):
                mask = np.arange(len(x)) != held
                coeff = model._robust_coeff(model._basis(x[mask], kind), y[mask], w[mask])
                predicted = float((model._basis(x[held:held+1], kind) @ coeff)[0])
                errors.append(abs(predicted-y[held])*width)
            comparison[kind] = float(np.mean(errors))
        split = max(6, int(len(x)*.7))
        if split < len(x):
            widths = np.array([s["screen_width"] for s in model.samples])
            for kind in ("linear", "quadratic", "sqrt"):
                coeff = model._robust_coeff(model._basis(x[:split], kind),
                                            y[:split], w[:split])
                residual = (model._basis(x[split:], kind) @ coeff - y[split:]) * widths[split:]
                chronological_holdout[kind] = {
                    "train_samples": split, "test_samples": len(x)-split,
                    "mae_pixels": float(np.mean(abs(residual))),
                    "median_absolute_error_pixels": float(np.median(abs(residual))),
                    "errors_over_20_pixels": int(np.count_nonzero(abs(residual) > 20))}
    report = {
        "window_capture_events": sum("capture" in e or "before_capture" in e for e in events),
        "real_press_trials": len(trials),
        "valid_landing_measurements": len(measured),
        "estimated_successes_among_measured": successes,
        "score_confirmed_unmeasured_successes": len(score_confirmed_unmeasured),
        "score_confirmed_successes_total": score_confirmed_successes,
        "verified_round_failures": len(rounds),
        "unresolved_trial_outcomes": max(0, len(trials)-score_confirmed_successes-len(rounds)),
        "confirmed_outcome_success_rate": score_confirmed_successes / (score_confirmed_successes+len(rounds)) if score_confirmed_successes+len(rounds) else None,
        "conservative_success_rate_all_trials": score_confirmed_successes / len(trials) if trials else None,
        "success_rate_all_trials": score_confirmed_successes / len(trials) if len(rounds) == len(trials)-score_confirmed_successes and trials else None,
        "mean_landing_error_pixels": float(np.mean([abs(e["measurement"]["landing_error"]) for e in measured])) if measured else None,
        "model": fit,
        "candidate_model_loo_mae_pixels": comparison,
        "candidate_model_chronological_holdout": chronological_holdout,
        "left_direction_model": model.fit(-1),
        "right_direction_model": model.fit(1),
        "completed_rounds": len(rounds),
        "simulation": simulation,
        "completed_round_scores": [r["score"] for r in rounds],
        "mean_score": float(np.mean([r["score"] for r in rounds])) if rounds else None,
        "highest_completed_score": max([r["score"] for r in rounds], default=None),
        "live_score_observations": live_scores,
        "highest_observed_score": max([r["score"] for r in rounds+live_scores], default=None),
        "highest_score": max([r["score"] for r in rounds+live_scores], default=None),
        "longest_success_streak": longest,
        "session_boundaries": boundaries,
        "completed_round_attempts": round_attempts,
        "open_round_attempts": current_attempts,
        "notes": ["有落点测量的成功由 HUD 分数变化和落地画面共同估计；无落点测量的成功仅由 HUD 分数变化确认，不进入距离模型。失败由结算截图验证。",
                  "分数由结算截图人工读取并附来源；无人值守自动分数 OCR 尚未实现。",
                  "缺失的实际落点绝不以目标距离代替。"]
    }
    (DATA / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    fig, ax = plt.subplots(figsize=(7, 4))
    if model.samples:
        xs = [s["seconds"] for s in model.samples]
        ys = [s["distance"] for s in model.samples]
        ax.scatter(xs, ys, c="tab:blue", label="Real measurements")
        if fit:
            grid = np.linspace(*fit["seconds_range"], 200)
            basis = model._basis(grid, fit["kind"])
            width = int(np.median([s["screen_width"] for s in model.samples]))
            ax.plot(grid, (basis @ np.array(fit["coefficients"])) * width,
                    c="tab:orange", label=f"{fit['kind']} fit")
        ax.legend()
    else:
        ax.text(.5, .5, "No valid real jump measurements", ha="center", va="center", transform=ax.transAxes)
    ax.set_xlabel("Actual press time (s)")
    ax.set_ylabel("Measured jump distance (px)")
    ax.set_title("Press time and jump distance: real data only")
    fig.tight_layout()
    fig.savefig(DATA / "press_distance.png", dpi=150)
    plt.close(fig)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
