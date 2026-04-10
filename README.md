# RoboPulse - Adaptive Risk Monitoring

**Control system for dynamic capital allocation.**

Adaptive **α / β / γ** tuning for [Shimi](https://github.com/carjam/shimi)-style loan allocation: metrics, alerts, Streamlit dashboard.

## Configuration

Config is a **single JSON file** (default: `config/default.json`). Paths under `data` are resolved **relative to the config file’s directory** (absolute paths are allowed).

### Simulation timeline

| Field | Role |
|-------|------|
| `simulation_start_date` | Calendar anchor (`YYYY-MM-DD`); loan dates advance from here using `loans_per_calendar_day`. |
| `loans_per_calendar_day` | Loans per simulated day; drives calendar dates and exhaustion-date predictions. |

### Signals, tolerances, and when γ applies

| Field | Role |
|-------|------|
| `rolling_loans_for_share_deviation` | Rolling window length (in loans) for **max lender share deviation** vs targets—feeds **α** adjustments. |
| `max_abs_share_deviation` | **Cap** on tolerated deviation; above it **α** is increased; well below it **α** decays. |
| `fico_epsilon_pct` | **Tolerance** on worst lender **FICO vs book mean** (relative); outside band drives **γ** up or down. |
| `fico_gamma_min_total_funded_fraction` | **γ** stays at `0` until total funded face reaches this fraction of **pool commitment**; then FICO fairness is active. |

### Controller cadence and β mode

| Field | Role |
|-------|------|
| `reevaluation_every_n_loans` | Run the adaptive update (`adjust_params`) every **N** loans (minimum `1`). Larger **N** makes **α / β / γ** change less often. |
| `simultaneous_exhaustion` | When `true` and `target_exhaustion_date_by_lender` is **`null`**, **β** responds to **exhaustion spread** (days) across lenders’ predicted run-out dates. |
| `target_exhaustion_date_by_lender` | Optional map of lender id → `YYYY-MM-DD`. When **set**, the automatic **β** rule tied to exhaustion spread is **not** applied (extension point for a different policy). |

### Initial allocation parameters (`allocation_params`)

Passed into Shimi as starting **AllocationParams**: **`alpha`** (share tracking), **`beta`** (exhaustion alignment), **`gamma_fico`** (FICO fairness), **`participation_floor`** (minimum participation weighting).

### Bounds (`param_bounds`)

**`alpha_*`, `beta_*`, `gamma_*`**: min/max **clips** after each controller step so tuned weights stay in a safe range.

### Gains (`controller_gains`)

Multiplicative **control law** on violations vs calm periods (each applied with the bounds above):

| Field | Role |
|-------|------|
| `alpha_on_share_violation` | Scale **α** up when share deviation exceeds `max_abs_share_deviation`. |
| `beta_on_exhaustion_spread` | Scale **β** up when exhaustion spread is high (when the β rule is active). |
| `gamma_on_fico_violation` | Scale **γ** up when FICO deviation exceeds `fico_epsilon_pct`. |
| `gamma_seed_on_fico_violation` | First **γ** bump when **γ** was ~0 and FICO violates tolerance. |
| `decay_when_within_tolerance` | Gentle **decay** for **α / β / γ** when the corresponding signal is comfortably inside tolerance. |

### Data (`data`)

| Field | Role |
|-------|------|
| `lenders_csv` | Lender program (commitments, targets, etc.) for Shimi. |
| `loans_csv` | Loan tape columns consumed by the simulator (e.g. `loan_index`, `loan_fico`, per-lender columns). |

### Dashboard alerts (Streamlit)

| Field | Role |
|-------|------|
| `infeasibility_alert_window_loans` | Trailing window length for **infeasibility rate** (share of infeasible allocations in the window). |
| `infeasibility_alert_rate_max` | Charts highlight when the window **infeasibility rate** exceeds this value. |

**Install:** `pip install -r requirements.txt && pip install -e .` (Shimi: `-e ../shimi` or `ROBOPULSE_SHIMI_ROOT`). **UI:** `streamlit run streamlit_app.py` — slider, **+1** (wrap), **Autoplay** (~1.2s, wrap). Demo tape: `data/demo_loans.csv`. **Config:** `config/default.json`.

**License:** [MIT](LICENSE).
