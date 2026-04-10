"""RoboPulse Streamlit UI."""

from __future__ import annotations

import sys
import time
from datetime import timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from robopulse.config import load_config
from robopulse.paths import robopulse_repo_root
from robopulse.runner import run_simulation


def _data_revision(cfg_path: Path) -> tuple[int, int, int]:
    cfg = load_config(str(cfg_path))
    return (
        cfg_path.stat().st_mtime_ns,
        cfg.data.lenders_csv.stat().st_mtime_ns,
        cfg.data.loans_csv.stat().st_mtime_ns,
    )


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


@st.cache_data(show_spinner="Running simulation…")
def _cached_simulation(
    config_path_str: str,
    _data_revision: tuple[int, int, int],
) -> tuple[pd.DataFrame, dict, object]:
    cfg = load_config(config_path_str)
    trace, summary = run_simulation(cfg)
    return trace, summary, cfg


cfg_path = robopulse_repo_root() / "config" / "default.json"
trace, summary, cfg = _cached_simulation(str(cfg_path), _data_revision(cfg_path))

if trace.empty:
    st.error("Simulation produced no rows — check data paths in config.")
    st.stop()

full = trace.dropna(subset=["loan_index"], how="all").sort_values("loan_index", ignore_index=True)
idx_min = int(full["loan_index"].min())
idx_max = int(full["loan_index"].max())
_span = idx_max - idx_min + 1


def _advance_loan_wrap() -> None:
    """+1 loan index, wrap; writes ``rp_tape_end`` (not a widget key)."""
    cur = int(st.session_state["rp_tape_end"])
    st.session_state["rp_tape_end"] = idx_min + (cur - idx_min + 1) % _span
    st.session_state["_rp_need_slider_sync"] = True


def _rewind_to_start() -> None:
    """Jump visible end to the first loan on the tape (minimum ``loan_index``)."""
    st.session_state["rp_tape_end"] = idx_min
    st.session_state["_rp_need_slider_sync"] = True


if "rp_tape_end" not in st.session_state:
    st.session_state.rp_tape_end = idx_max
else:
    st.session_state.rp_tape_end = max(idx_min, min(idx_max, int(st.session_state.rp_tape_end)))

if "rp_slider_loan" not in st.session_state:
    st.session_state.rp_slider_loan = int(st.session_state.rp_tape_end)

if st.session_state.pop("_rp_need_slider_sync", False):
    st.session_state.rp_slider_loan = int(st.session_state.rp_tape_end)

st.markdown("##### Tape scrubber")
ctrl, slide = st.columns([0.22, 0.78], gap="medium")
with ctrl:
    st.caption("Playback")
    r0, r1, r2 = st.columns(3)
    with r0:
        st.button(
            "⏮",
            key="rp_rewind_start",
            help="Rewind to first loan (tape start).",
            on_click=_rewind_to_start,
            use_container_width=True,
        )
    with r1:
        st.button("⏭ +1", key="rp_step_one", on_click=_advance_loan_wrap, use_container_width=True)
    with r2:
        st.toggle("Autoplay", key="rp_autoplay")

with slide:
    st.slider("Loan index (visible end)", min_value=idx_min, max_value=idx_max, key="rp_slider_loan")

st.session_state["rp_tape_end"] = int(st.session_state["rp_slider_loan"])

# Full-tape alerts omitted while the scrubber sits on the first loan (replay start).
_at_replay_start = idx_max > idx_min and int(st.session_state["rp_tape_end"]) == idx_min
if not _at_replay_start:
    _alerts: list[str] = []
    if "infeasibility_rate_window" in full.columns:
        bi = full["infeasibility_rate_window"] > cfg.infeasibility_alert_rate_max
        if bi.any():
            _alerts.append(f"Infeas. rate: **{int(bi.sum())}** loans (full tape).")
    if "worst_fico_pct_dev" in full.columns:
        bf = full["worst_fico_pct_dev"] > cfg.fico_epsilon_pct
        if bf.any():
            _alerts.append(f"FICO ε: **{int(bf.sum())}** loans (full tape).")
    if _alerts:
        st.warning("\n".join(_alerts))
    else:
        st.success("No alerts on full replay.")


def _maybe_autoplay_advance() -> None:
    if not st.session_state.get("rp_autoplay"):
        return
    now = time.monotonic()
    last = st.session_state.get("_rp_autoplay_mono")
    if last is None:
        st.session_state["_rp_autoplay_mono"] = now
        return
    if now - last >= 1.05:
        st.session_state["_rp_autoplay_mono"] = now
        _advance_loan_wrap()
        # Fragments cannot mutate another widget's key (`rp_slider_loan`); full rerun syncs it.
        st.rerun()


@st.fragment(run_every=timedelta(seconds=1.2))
def _tape_chart_fragment() -> None:
    # Chart in fragment so `run_every` redraws it; `rp_tape_end` is not a slider key.
    _maybe_autoplay_advance()

    end_loan = int(st.session_state["rp_tape_end"])
    t = full[full["loan_index"] <= end_loan].copy()
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
        title=dict(
            text=f"Visible: loans {idx_min} … {end_loan} ({len(t)} of {len(full)} rows)",
            font=dict(size=14, color="#94a3b8"),
            x=0,
            xanchor="left",
        ),
    )

    fig.update_xaxes(title_text="Calendar date", row=4, col=1)

    st.plotly_chart(fig, use_container_width=True)


_tape_chart_fragment()

st.caption(f"Tape: {summary.get('total_loans', 0)} loans · Infeas: {summary.get('infeasible_loans', 0)} · `{cfg_path}`")
