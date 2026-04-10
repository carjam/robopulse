from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ParamBounds:
    alpha_min: float
    alpha_max: float
    beta_min: float
    beta_max: float
    gamma_min: float
    gamma_max: float


@dataclass
class ControllerGains:
    alpha_on_share_violation: float
    beta_on_exhaustion_spread: float
    gamma_on_fico_violation: float
    decay_when_within_tolerance: float
    gamma_seed_on_fico_violation: float = 0.12


@dataclass
class AllocationParamsConfig:
    alpha: float
    beta: float
    gamma_fico: float
    participation_floor: float


@dataclass
class DataPaths:
    lenders_csv: Path
    loans_csv: Path


@dataclass
class RoboPulseConfig:
    simulation_start_date: str
    loans_per_calendar_day: float
    rolling_loans_for_share_deviation: int
    max_abs_share_deviation: float
    fico_epsilon_pct: float
    fico_gamma_min_total_funded_fraction: float
    reevaluation_every_n_loans: int
    simultaneous_exhaustion: bool
    target_exhaustion_date_by_lender: dict[str, str] | None
    infeasibility_alert_rate_max: float
    infeasibility_alert_window_loans: int
    allocation_params: AllocationParamsConfig
    param_bounds: ParamBounds
    controller_gains: ControllerGains
    data: DataPaths


def _parse(d: dict[str, Any], *, base_dir: Path) -> RoboPulseConfig:
    data_raw = d["data"]

    def resolve(p: str) -> Path:
        path = Path(p)
        if path.is_absolute():
            return path
        return (base_dir / path).resolve()

    return RoboPulseConfig(
        simulation_start_date=str(d["simulation_start_date"]),
        loans_per_calendar_day=float(d["loans_per_calendar_day"]),
        rolling_loans_for_share_deviation=int(d["rolling_loans_for_share_deviation"]),
        max_abs_share_deviation=float(d["max_abs_share_deviation"]),
        fico_epsilon_pct=float(d["fico_epsilon_pct"]),
        fico_gamma_min_total_funded_fraction=float(d["fico_gamma_min_total_funded_fraction"]),
        reevaluation_every_n_loans=max(1, int(d["reevaluation_every_n_loans"])),
        simultaneous_exhaustion=bool(d["simultaneous_exhaustion"]),
        target_exhaustion_date_by_lender=d.get("target_exhaustion_date_by_lender"),
        infeasibility_alert_rate_max=float(d["infeasibility_alert_rate_max"]),
        infeasibility_alert_window_loans=max(1, int(d["infeasibility_alert_window_loans"])),
        allocation_params=AllocationParamsConfig(**d["allocation_params"]),
        param_bounds=ParamBounds(**d["param_bounds"]),
        controller_gains=ControllerGains(**d["controller_gains"]),
        data=DataPaths(
            lenders_csv=resolve(data_raw["lenders_csv"]),
            loans_csv=resolve(data_raw["loans_csv"]),
        ),
    )


def load_config(path: str | Path) -> RoboPulseConfig:
    p = Path(path).resolve()
    raw = json.loads(p.read_text(encoding="utf-8"))
    return _parse(raw, base_dir=p.parent)
