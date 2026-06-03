"""
ui/app.py — Streamlit dashboard for pyvar.com

Reasoning:
- Streamlit lets us build the parameter input form and result visualisation
  in pure Python, without a separate React/JS frontend.
- The UI calls the FastAPI REST API rather than importing engine modules
  directly. This keeps the UI stateless and the compute isolated to workers.
- Polling loop: after submitting, the UI polls GET /var/result/{task_id}
  every second using st.rerun() until the job is complete.
- Plotly renders the full loss distribution as a histogram + VaR/CVaR
  threshold lines — the key visualisation for a VaR platform.
- st.session_state persists task_id and result across Streamlit reruns.
"""

from __future__ import annotations

import time

import numpy as np
import plotly.graph_objects as go
import requests
import streamlit as st

from ingestion.fixtures import generate_gbm_returns

# ── Config ─────────────────────────────────────────────────────────────────────
API_BASE = "http://localhost:8000/api/v1"
DEV_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."  # nosec B105 # replace with real token in production
)

HEADERS = {"Authorization": f"Bearer {DEV_TOKEN}"}

# ── Page setup ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="pyvar.com — Monte Carlo VaR",
    page_icon="📊",
    layout="wide",
)

st.title("pyvar.com")
st.caption("Open-source Monte Carlo Value at Risk · powered by NumPy & Numba")

# ── Sidebar: Parameter input form ──────────────────────────────────────────────
with st.sidebar:
    st.header("Parameters")

    portfolio_value = st.number_input(
        "Portfolio value (£)",
        min_value=1_000.0,
        max_value=1_000_000_000.0,
        value=1_000_000.0,
        step=10_000.0,
        format="%.0f",
    )

    confidence_level = st.selectbox(
        "Confidence level",
        options=[0.90, 0.95, 0.975, 0.99, 0.995],
        index=3,
        format_func=lambda x: f"{x*100:.1f}%",
        help="0.99 = Basel III standard, 0.975 = FRTB Expected Shortfall",
    )

    horizon_days = st.selectbox(
        "Horizon (trading days)",
        options=[1, 5, 10, 22],
        index=0,
        format_func=lambda x: f"{x}d",
        help="1d = daily VaR, 10d = Basel III regulatory horizon",
    )

    n_simulations = st.select_slider(
        "Simulations",
        options=[1_000, 10_000, 50_000, 100_000, 250_000, 500_000],
        value=100_000,
        format_func=lambda x: f"{x:,}",
    )

    st.divider()
    st.caption("Returns series")
    use_synthetic = st.checkbox("Use synthetic GBM returns", value=True)

    if use_synthetic:
        n_obs = st.slider("History length (days)", 60, 504, 252)
        vol_pct = st.slider("Volatility (% ann.)", 5, 50, 18)
        returns = generate_gbm_returns(
            n_obs=n_obs,
            mu=0.0003,
            sigma=vol_pct / 100 / np.sqrt(252),
            seed=42,
        ).tolist()
        st.caption(f"{len(returns)} observations loaded")
    else:
        st.info("Paste CSV returns or connect to data source (coming soon).")
        st.stop()

    submitted = st.button("Run VaR", type="primary", use_container_width=True)

# ── Main panel ─────────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

# Initialise session state
if "task_id" not in st.session_state:
    st.session_state.task_id = None
if "result" not in st.session_state:
    st.session_state.result = None

# Submit job
if submitted:
    st.session_state.result = None
    payload = {
        "portfolio_value": portfolio_value,
        "returns": returns,
        "confidence_level": confidence_level,
        "horizon_days": horizon_days,
        "n_simulations": n_simulations,
        "seed": 42,
    }

    try:
        resp = requests.post(f"{API_BASE}/var/compute", json=payload, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        st.session_state.task_id = resp.json()["task_id"]
        st.info(f"Job submitted · task_id: `{st.session_state.task_id}`")
    except requests.RequestException as e:
        st.error(f"API error: {e}")

# Poll for result
if st.session_state.task_id and not st.session_state.result:
    with st.spinner("Computing…"):
        for _ in range(60):  # timeout after 60 seconds
            try:
                r = requests.get(
                    f"{API_BASE}/var/result/{st.session_state.task_id}",
                    headers=HEADERS,
                    timeout=5,
                )
                data = r.json()
                if data["status"] == "success":
                    st.session_state.result = data["result"]
                    break
                elif data["status"] == "failure":
                    st.error(f"Computation failed: {data.get('error')}")
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        else:
            st.warning("Computation timed out — try fewer simulations.")

# Display results
if st.session_state.result:
    r = st.session_state.result

    with col1:
        st.metric("VaR (abs)", f"£{r['var_abs']:,.0f}", f"{r['var_pct']*100:.2f}%")
    with col2:
        st.metric("CVaR / ES (abs)", f"£{r['cvar_abs']:,.0f}", f"{r['cvar_pct']*100:.2f}%")
    with col3:
        st.metric("Daily vol (σ)", f"{r['sigma']*100:.2f}%")
    with col4:
        st.metric("Simulations", f"{r['n_simulations']:,}")

    st.divider()

    # ── Loss distribution chart ───────────────────────────────────────────────
    loss_dist = np.array(r["loss_dist"])
    loss_pct = loss_dist * 100  # convert to percentage for readability

    var_line = r["var_pct"] * 100
    cvar_line = r["cvar_pct"] * 100

    fig = go.Figure()

    fig.add_trace(
        go.Histogram(
            x=loss_pct,
            nbinsx=120,
            name="Loss distribution",
            marker_color="#378ADD",
            opacity=0.75,
        )
    )

    fig.add_vline(
        x=var_line,
        line_dash="dash",
        line_color="#E24B4A",
        annotation_text=f"VaR {confidence_level*100:.0f}% = {var_line:.2f}%",
        annotation_position="top right",
    )

    fig.add_vline(
        x=cvar_line,
        line_dash="dot",
        line_color="#BA7517",
        annotation_text=f"CVaR = {cvar_line:.2f}%",
        annotation_position="top left",
    )

    fig.update_layout(
        title=f"Monte Carlo loss distribution · {r['n_simulations']:,} paths · "
        f"{confidence_level*100:.0f}% confidence · {horizon_days}d horizon",
        xaxis_title="Loss (% of portfolio)",
        yaxis_title="Frequency",
        template="plotly_white",
        showlegend=False,
        margin=dict(t=60, b=40, l=40, r=40),
        height=420,
    )

    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Raw result JSON"):
        st.json({k: v for k, v in r.items() if k != "loss_dist"})
