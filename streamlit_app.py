"""RoboPulse monitoring dashboard — read-only time series (no user inputs)."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `streamlit run streamlit_app.py` without editable install during dev.
_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from robopulse.config import load_config
from robopulse.paths import robopulse_repo_root
from robopulse.runner import run_simulation

st.set_page_config(page_title="RoboPulse", layout="wide")

st.markdown(
    """
    <style>
    .rp-hero { font-size: 1.75rem; font-weight: 700; letter-spacing: -0.02em;
      background: linear-gradient(90deg, #00c6ff 0%, #7b2cbf 100%);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    .rp-sub { color: #94a3b8; font-size: 0.95rem; margin-top: 0.25rem; }
    </style>
    <div class="rp-hero">RoboPulse</div>
    <div class="rp-sub">Allocation heartbeat · adaptive α, β, γ · risk monitoring</div>
    """,
    unsafe_allow_html=True,
)

cfg_path = robopulse_repo_root() / "config" / "default.json"
cfg = load_config(cfg_path)

trace, summary = run_simulation(cfg)

if trace.empty:
    st.error("Simulation produced no rows — check data paths in config.")
    st.stop()

t = trace.dropna(subset=["loan_index"], how="all")
x = t["calendar_date"]

fig = make_subplots(
    rows=4,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.06,
    subplot_titles=(
        "QP weights (α, β, γ)",
        "Share fit — rolling max |s−t| vs cap",
        "FICO — worst % deviation vs group mean",
        "Splits & risk — Gini (monitor) · infeasibility window rate",
    ),
)

fig.add_trace(
    go.Scatter(x=x, y=t["alpha"], name="α", line=dict(color="#00c6ff", width=2)),
    row=1,
    col=1,
)
fig.add_trace(
    go.Scatter(x=x, y=t["beta"], name="β", line=dict(color="#7b2cbf", width=2)),
    row=1,
    col=1,
)
fig.add_trace(
    go.Scatter(x=x, y=t["gamma_fico"], name="γ", line=dict(color="#f472b6", width=2)),
    row=1,
    col=1,
)

cap = cfg.max_abs_share_deviation
fig.add_trace(
    go.Scatter(
        x=x,
        y=t["rolling_max_share_dev"],
        name="Rolling max share dev",
        line=dict(color="#38bdf8"),
    ),
    row=2,
    col=1,
)
fig.add_hline(y=cap, line_dash="dash", line_color="#fbbf24", row=2, col=1, annotation_text="cap")

fig.add_trace(
    go.Scatter(
        x=x,
        y=t["worst_fico_pct_dev"],
        name="Worst FICO % vs mean",
        line=dict(color="#a78bfa"),
    ),
    row=3,
    col=1,
)
fig.add_hline(
    y=cfg.fico_epsilon_pct,
    line_dash="dash",
    line_color="#f87171",
    row=3,
    col=1,
    annotation_text="ε",
)

fig.add_trace(
    go.Scatter(x=x, y=t["gini_split"], name="Gini (loan split)", line=dict(color="#34d399")),
    row=4,
    col=1,
)
fig.add_trace(
    go.Scatter(
        x=x,
        y=t["infeasibility_rate_window"],
        name="Infeas. rate (window)",
        line=dict(color="#fb7185"),
    ),
    row=4,
    col=1,
)

fig.update_layout(
    height=980,
    showlegend=True,
    template="plotly_dark",
    paper_bgcolor="#0f172a",
    plot_bgcolor="#0f172a",
    font=dict(color="#e2e8f0"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(l=48, r=24, t=48, b=48),
)

fig.update_xaxes(title_text="Calendar date", row=4, col=1)

st.plotly_chart(fig, use_container_width=True)

alerts = []
if "infeasibility_rate_window" in t.columns:
    bad = t["infeasibility_rate_window"] > cfg.infeasibility_alert_rate_max
    if bad.any():
        alerts.append(
            f"Infeasibility window rate exceeded **{cfg.infeasibility_alert_rate_max:.0%}** on "
            f"**{int(bad.sum())}** loan(s) (alert-only)."
        )
if "worst_fico_pct_dev" in t.columns:
    bad_f = t["worst_fico_pct_dev"] > cfg.fico_epsilon_pct
    if bad_f.any():
        alerts.append(
            f"FICO band ε exceeded on **{int(bad_f.sum())}** loan(s) after γ is active (review γ and priors)."
        )

if alerts:
    st.warning("\n\n".join(alerts))
else:
    st.success("No threshold alerts on this replay (see chart annotations for caps).")

st.caption(
    f"Loans: **{summary.get('total_loans', 0)}** · Infeasible steps: **{summary.get('infeasible_loans', 0)}** · "
    f"Config: `{cfg_path}`"
)
