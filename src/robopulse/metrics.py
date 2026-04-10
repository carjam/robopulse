from __future__ import annotations

import numpy as np
import pandas as pd


def per_lender_abs_share_deviation(
    shares: dict[str, float],
    target_shares: dict[str, float],
) -> dict[str, float]:
    return {k: abs(float(shares[k]) - float(target_shares[k])) for k in shares}


def rolling_max_per_lender_deviation(
    history: list[dict[str, float]],
    window: int,
) -> float | None:
    """Max over lenders of rolling max of |s_i - t_i| over last `window` loans."""
    if not history or window < 1:
        return None
    recent = history[-window:]
    ids = list(recent[0].keys())
    worst = 0.0
    for lid in ids:
        local_max = max(float(row[lid]) for row in recent)
        worst = max(worst, local_max)
    return float(worst)


def portfolio_wafico_by_lender(
    funded: dict[str, float],
    fico_weighted: dict[str, float],
) -> dict[str, float]:
    out: dict[str, float] = {}
    for lid in funded:
        a = float(funded[lid])
        if a <= 1e-12:
            out[lid] = float("nan")
        else:
            out[lid] = float(fico_weighted[lid]) / a
    return out


def fico_relative_deviations_vs_mean(
    wafico: dict[str, float],
) -> dict[str, float]:
    """For each lender: |w_i - mu| / mu * 100 with mu = mean of finite waficos."""
    vals = [v for v in wafico.values() if np.isfinite(v)]
    if not vals:
        return {k: float("nan") for k in wafico}
    mu = float(np.mean(vals))
    if mu <= 1e-9:
        return {k: float("nan") for k in wafico}
    return {k: abs(float(wafico[k]) - mu) / mu * 100.0 if np.isfinite(wafico[k]) else float("nan") for k in wafico}


def total_funded_face(program_funded_from_prior: dict[str, float]) -> float:
    return float(sum(float(v) for v in program_funded_from_prior.values()))


def predicted_exhaustion_date_offsets(
    *,
    remaining: dict[str, float],
    mean_daily_draw: dict[str, float],
    loans_per_calendar_day: float,
) -> dict[str, float]:
    """Days from now until exhaustion: remaining / (mean allocation per loan * loans_per_day)."""
    out: dict[str, float] = {}
    for lid, rem in remaining.items():
        md = max(float(mean_daily_draw.get(lid, 0.0)), 1e-9)
        daily = md * float(loans_per_calendar_day)
        out[lid] = float(rem) / daily
    return out


def exhaustion_spread_days(offsets: dict[str, float]) -> float:
    finite = [v for v in offsets.values() if np.isfinite(v)]
    if len(finite) < 2:
        return 0.0
    return float(max(finite) - min(finite))


def rolling_mean_draw(history_amounts: pd.DataFrame, lender_ids: list[str], window: int) -> dict[str, float]:
    """Mean allocated face per loan over last `window` rows (or all if shorter)."""
    if history_amounts.shape[0] == 0:
        return {lid: 0.0 for lid in lender_ids}
    sub = history_amounts[lender_ids].tail(window)
    return {lid: float(sub[lid].mean()) for lid in lender_ids}
