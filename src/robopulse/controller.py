from __future__ import annotations

from dataclasses import replace

from robopulse.config import RoboPulseConfig

# Imported lazily in adjust() to avoid import errors if shimi not installed at module load in tests.


def _clip(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))


def adjust_params(
    cfg: RoboPulseConfig,
    params: "AllocationParams",  # noqa: F821
    *,
    rolling_max_share_dev: float | None,
    worst_fico_pct_dev: float | None,
    exhaustion_spread_days: float,
    gamma_active: bool,
) -> "AllocationParams":
    from shimi.allocation.engine import AllocationParams

    b = cfg.param_bounds
    g = cfg.controller_gains
    p = params
    decay = g.decay_when_within_tolerance

    alpha = p.alpha
    beta = p.beta
    gamma = p.gamma_fico

    cap = cfg.max_abs_share_deviation
    eps = cfg.fico_epsilon_pct

    if rolling_max_share_dev is not None and rolling_max_share_dev > cap:
        alpha = _clip(alpha * g.alpha_on_share_violation, b.alpha_min, b.alpha_max)
    elif rolling_max_share_dev is not None and rolling_max_share_dev < cap * 0.5:
        alpha = _clip(alpha * decay, b.alpha_min, b.alpha_max)

    if cfg.simultaneous_exhaustion and cfg.target_exhaustion_date_by_lender is None:
        if exhaustion_spread_days > 0.25:
            beta = _clip(beta * g.beta_on_exhaustion_spread, b.beta_min, b.beta_max)
        else:
            beta = _clip(beta * decay, b.beta_min, b.beta_max)

    if gamma_active and worst_fico_pct_dev is not None and worst_fico_pct_dev > eps:
        if gamma < 1e-12:
            gamma = _clip(g.gamma_seed_on_fico_violation, b.gamma_min, b.gamma_max)
        else:
            gamma = _clip(gamma * g.gamma_on_fico_violation, b.gamma_min, b.gamma_max)
    elif gamma_active and worst_fico_pct_dev is not None and worst_fico_pct_dev < eps * 0.5:
        gamma = _clip(gamma * decay, b.gamma_min, b.gamma_max)

    return replace(
        p,
        alpha=alpha,
        beta=beta,
        gamma_fico=gamma,
    )


def to_shimi_params(cfg: RoboPulseConfig) -> "AllocationParams":
    from shimi.allocation.engine import AllocationParams

    a = cfg.allocation_params
    return AllocationParams(
        alpha=a.alpha,
        beta=a.beta,
        gamma_fico=a.gamma_fico,
        participation_floor=a.participation_floor,
    )
