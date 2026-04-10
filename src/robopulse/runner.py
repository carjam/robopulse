from __future__ import annotations

import datetime as dt
from dataclasses import asdict, replace
from typing import Any

import numpy as np
import pandas as pd

from robopulse.config import RoboPulseConfig
from robopulse.controller import adjust_params, to_shimi_params
from robopulse.metrics import (
    exhaustion_spread_days,
    fico_relative_deviations_vs_mean,
    per_lender_abs_share_deviation,
    portfolio_wafico_by_lender,
    predicted_exhaustion_date_offsets,
    rolling_max_per_lender_deviation,
    rolling_mean_draw,
    total_funded_face,
)

from shimi.allocation.engine import AllocationParams, allocate_loan
from shimi.data.loaders import load_lender_program_from_csv, load_loan_tape_from_csv
from shimi.data.models import LenderProgram, PortfolioPrior
from shimi.data.tape import portfolio_prior_from_loan_tape
from shimi.metrics import gini_of_loan_split


def _pool_total_commitment(program: LenderProgram) -> float:
    return float(sum(l.total_commitment for l in program.lenders.values()))


def run_simulation(cfg: RoboPulseConfig) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Replay the loan tape with adaptive parameters; return trace frame and summary."""
    program = load_lender_program_from_csv(cfg.data.lenders_csv)
    tape = load_loan_tape_from_csv(cfg.data.loans_csv)
    tape = tape.sort_values("loan_index", ignore_index=True)

    ids = sorted(program.lenders.keys())
    target_shares = {lid: float(program.lenders[lid].target_share) for lid in ids}

    params = to_shimi_params(cfg)
    pool = _pool_total_commitment(program)

    rows: list[dict[str, Any]] = []
    share_dev_history: list[dict[str, float]] = []
    infeas_flags: list[bool] = []

    start = dt.date.fromisoformat(cfg.simulation_start_date)

    for _, row in tape.iterrows():
        loan_index = int(row["loan_index"])
        loan_fico = float(row["loan_fico"])
        lender_cols = [c for c in tape.columns if c not in ("loan_index", "loan_fico")]
        loan_amount = float(sum(float(row[c]) for c in lender_cols))

        prior: PortfolioPrior | None = None
        if program.history.shape[0] > 0:
            prior = portfolio_prior_from_loan_tape(program.history, ids)

        funded_prior = prior.funded_face_by_lender if prior is not None else {lid: 0.0 for lid in ids}
        fico_w_prior = prior.fico_weighted_face_by_lender if prior is not None else {lid: 0.0 for lid in ids}
        tot_funded = total_funded_face(funded_prior)
        gamma_active = tot_funded >= cfg.fico_gamma_min_total_funded_fraction * pool

        if not gamma_active:
            params = replace(params, gamma_fico=0.0)

        infeas = False
        res = None
        try:
            res = allocate_loan(
                program.clone(),
                loan_amount,
                params,
                loan_fico=loan_fico,
                portfolio_prior=prior,
            )
        except (ValueError, RuntimeError):
            infeas = True

        infeas_flags.append(infeas)

        offset_days = int(loan_index / max(cfg.loans_per_calendar_day, 1e-9))
        sim_date = start + dt.timedelta(days=offset_days)

        if infeas or res is None:
            rows.append(
                {
                    "loan_index": loan_index,
                    "calendar_date": sim_date.isoformat(),
                    "loan_amount": loan_amount,
                    "loan_fico": loan_fico,
                    "infeasible": True,
                    "alpha": params.alpha,
                    "beta": params.beta,
                    "gamma_fico": params.gamma_fico,
                    "rolling_max_share_dev": np.nan,
                    "worst_fico_pct_dev": np.nan,
                    "exhaustion_spread_days": np.nan,
                    "gini_split": np.nan,
                    "infeasibility_rate_window": np.nan,
                }
            )
            continue

        devs = per_lender_abs_share_deviation(res.shares, target_shares)
        share_dev_history.append(devs)
        win = cfg.rolling_loans_for_share_deviation
        rmax = rolling_max_per_lender_deviation(share_dev_history, win)

        wafico = portfolio_wafico_by_lender(
            {lid: funded_prior[lid] + res.amounts_by_lender[lid] for lid in ids},
            {lid: fico_w_prior[lid] + res.amounts_by_lender[lid] * loan_fico for lid in ids},
        )
        fdevs = fico_relative_deviations_vs_mean(wafico)
        worst_fico = max((v for v in fdevs.values() if np.isfinite(v)), default=np.nan)

        hist_amt = program.history
        mean_draw = rolling_mean_draw(hist_amt, ids, win) if hist_amt.shape[0] else {lid: 0.0 for lid in ids}
        for lid in ids:
            if hist_amt.shape[0] == 0:
                mean_draw[lid] = res.amounts_by_lender[lid]
            elif mean_draw[lid] < 1e-12:
                mean_draw[lid] = res.amounts_by_lender[lid]

        rem_after = {lid: program.lenders[lid].remaining_commitment - res.amounts_by_lender[lid] for lid in ids}
        offsets = predicted_exhaustion_date_offsets(
            remaining=rem_after,
            mean_daily_draw=mean_draw,
            loans_per_calendar_day=cfg.loans_per_calendar_day,
        )
        ex_spread = exhaustion_spread_days(offsets)

        gini = gini_of_loan_split(res.amounts_by_lender, lender_ids=ids)

        program.apply_loan_allocation(res.amounts_by_lender, loan_index=loan_index, loan_fico=loan_fico)

        w_lo = min(cfg.infeasibility_alert_window_loans, len(infeas_flags))
        recent = infeas_flags[-w_lo:]
        inf_rate = sum(recent) / len(recent) if recent else 0.0

        rows.append(
            {
                "loan_index": loan_index,
                "calendar_date": sim_date.isoformat(),
                "loan_amount": loan_amount,
                "loan_fico": loan_fico,
                "infeasible": False,
                "alpha": params.alpha,
                "beta": params.beta,
                "gamma_fico": params.gamma_fico,
                "rolling_max_share_dev": rmax,
                "worst_fico_pct_dev": worst_fico,
                "exhaustion_spread_days": ex_spread,
                "gini_split": gini,
                "infeasibility_rate_window": inf_rate,
            }
        )

        if (loan_index + 1) % cfg.reevaluation_every_n_loans == 0:
            p_last = params
            params = adjust_params(
                cfg,
                p_last,
                rolling_max_share_dev=rmax,
                worst_fico_pct_dev=worst_fico if gamma_active else None,
                exhaustion_spread_days=ex_spread,
                gamma_active=gamma_active,
            )

    trace = pd.DataFrame(rows)
    summary = {
        "total_loans": int(len(trace)),
        "infeasible_loans": int(trace["infeasible"].sum()) if "infeasible" in trace.columns else 0,
        "initial_params": asdict(cfg.allocation_params),
    }
    if not trace.empty and not trace["alpha"].isna().all():
        summary["final_alpha"] = float(trace["alpha"].iloc[-1])
        summary["final_beta"] = float(trace["beta"].iloc[-1])
        summary["final_gamma"] = float(trace["gamma_fico"].iloc[-1])

    return trace, summary
