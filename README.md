# RoboPulse

**RoboPulse** is an allocation control layer for programs modeled with [Shimi](../shimi): it tunes Shimi’s QP weights (α, β, γ) on a configurable schedule toward risk targets—share fit, exhaustion timing, portfolio FICO bands—and surfaces **monitoring-only** alerts (Gini, infeasibility).

- **Product one-liner:** *The allocation heartbeat your risk desk can watch.*
- **Python:** 3.11+
- **Shimi:** install from a **local path** (default: sibling `../shimi`). Override with `ROBOPULSE_SHIMI_ROOT`.

## Install

```bash
cd robopulse
pip install -r requirements.txt
pip install -e .
```

If Shimi lives elsewhere:

```bash
set ROBOPULSE_SHIMI_ROOT=C:\path\to\shimi
pip install -e "%ROBOPULSE_SHIMI_ROOT%"
pip install -e .
```

## Dashboard (no manual inputs)

```bash
cd robopulse
streamlit run streamlit_app.py
```

Uses bundled default config and Shimi sample data paths resolved relative to this repo.

## Configuration

See `config/default.json`. Key fields: rolling windows, share deviation cap, FICO ε (per lender vs group mean), exhaustion alignment, reevaluation cadence (`1` = per loan when the controller runs), infeasibility alert threshold.
