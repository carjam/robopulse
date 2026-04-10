# RoboPulse - Adaptive Risk Monitoring

**Control system for dynamic capital allocation.**

Adaptive **α / β / γ** tuning for [Shimi](https://github.com/carjam/shimi)-style loan allocation: metrics, alerts, Streamlit dashboard.

## Control method and mathematics

### Shimi and RoboPulse

- **[Shimi](https://github.com/carjam/shimi)** (dependency) implements the **inner** problem: each loan is a **convex quadratic program (QP)** over lender **shares** $s$, with fixed policy weights $(\alpha,\beta,\gamma)$. The full objective, feasible set, and standard-form QP statement are in Shimi’s README: [**Technical primer: per-loan model (mathematical specification)**](https://github.com/carjam/shimi#technical-primer-per-loan-model-mathematical-specification).
- **RoboPulse** (this repo) wraps that solver in a **tape replay** and adds an **outer feedback loop**: it observes portfolio-level **signals** after each feasible allocation and **retunes** $(\alpha,\beta,\gamma)$ on a fixed schedule. It does **not** replace Shimi’s constraints or solver; it only changes the **objective weights** passed into `allocate_loan`.

---

### Inner loop (Shimi): per-loan convex QP

**Decision variables.** Lender shares $s \in \mathbb{R}^n$ with $\mathbf{1}^\top s = 1$, bounds from **remaining commitment** and **participation floor** $f_{\mathrm{floor}}$ (see Shimi for the polytope $\mathcal{F}$). If $\mathcal{F} = \emptyset$, the allocation is **infeasible** (RoboPulse records it and surfaces **infeasibility rate** in the UI).

**Objective (same symbols as code).** With nonnegative weights and standard Shimi terms,

$$
\min_{s \in \mathcal{F}} \quad \alpha \left\lVert s - t \right\rVert_2^2 + \beta \sum_{i \in \mathrm{CO}} \Bigl(\frac{L\, s_{i}}{r_{i}}\Bigr)^{2} + \gamma \cdot (\text{FICO fairness term}) + \mathrm{ridge} \left\lVert s \right\rVert_2^2 + \text{(tiny fallback)} .
$$

Here $t$ are **target shares**, $L$ is loan face, $r_{i}$ remaining commitment, and $\mathrm{CO}$ indexes **contractual originators**. The **γ** branch is either a **portfolio prior** imbalance penalty (cumulative funded FICO mass vs a common mean) or a **cold-start** pull toward equal shares, as implemented in `shimi.allocation.engine`. This is a **convex QP** (sum of weighted squared norms of affine functions of $s$); Shimi solves it with **CVXPY + OSQP**.

RoboPulse **does not** modify $\mathcal{F}$; it only updates $(\alpha,\beta,\gamma)$ between loans subject to **param_bounds** in config.

---

### Outer loop (RoboPulse): signals and multiplicative updates

After each **successful** allocation, RoboPulse computes **monitoring signals** (see `src/robopulse/metrics.py`). Let $s_{i}$ be realized share on the loan, $t_{i}$ target share, and $W$ the rolling window length `rolling_loans_for_share_deviation`.

**Share pressure (α channel).** Per-lender deviation $d_{i,k} = \lvert s_{i,k} - t_{i}\rvert$ at loan index $k$. The controller input is

$$
D_{\mathrm{roll}} = \max_{i} \; \max_{k^{\prime} \,\in\, \mathcal{K}_{W}} d_{i,k^{\prime}}
$$

where $\mathcal{K}_{W}$ is the set of loan indices in the last $W$ loans on the tape (same window as `rolling_loans_for_share_deviation`).

**FICO fairness pressure (γ channel).** After the loan, each lender has a **post-deal** weighted-average FICO $\widehat{\mathrm{FICO}}_{i}$ (from cumulative funded face and FICO-weighted face, including this allocation). Let $\mu$ be the **mean** of those averages across lenders. The implementation uses **percent deviation from that mean**:

$$
\delta_{i} = \frac{\left\lvert \widehat{\mathrm{FICO}}_{i} - \mu \right\rvert}{\mu} \times 100, \qquad \delta_{\mathrm{worst}} = \max_{i} \delta_{i}.
$$

**γ activation.** Until total funded face reaches `fico_gamma_min_total_funded_fraction` × **pool commitment**, RoboPulse forces $\gamma_{\mathrm{fico}} = 0$ regardless of $\delta_{\mathrm{worst}}$ (FICO term inactive in both controller and Shimi objective for that phase).

**Exhaustion alignment (β channel).** Let $\mathrm{rem}_{i}$ be remaining commitment after the loan, $\bar{m}_{i}$ mean allocated face per loan over a trailing window, and `loans_per_calendar_day` = $\lambda$. Predicted **days-to-exhaustion** offsets (same units as code):

$$
T_{i} = \frac{\mathrm{rem}_{i}}{\bar{m}_{i} \, \lambda}.
$$

**Exhaustion spread** is $E = \max_{i} T_{i} - \min_{i} T_{i}$ (finite offsets only; degenerate cases return $0$).

**Discrete-time controller.** Let $c$ be the **cap** threshold from `max_abs_share_deviation`, let $\varepsilon$ match `fico_epsilon_pct`, and let $g_{\alpha}, g_{\beta}, g_{\gamma}, g_{\mathrm{seed}}, \rho$ be the gains from `controller_gains` (with **decay** $\rho$ from `decay_when_within_tolerance`). On each **reevaluation** step (every `reevaluation_every_n_loans` loans), `adjust_params` applies **multiplicative** rules with **clipping** to `[param_bounds]`:

| Signal | Tighten (increase weight) | Relax (decay) |
|--------|---------------------------|----------------|
| **α** | If $D_{\mathrm{roll}} > c$: $\alpha \leftarrow \mathrm{clip}(\alpha \cdot g_{\alpha})$ | Else if $D_{\mathrm{roll}} < c/2$: $\alpha \leftarrow \mathrm{clip}(\alpha \cdot \rho)$ |
| **β** | If `simultaneous_exhaustion` and no fixed target dates: if $E > 0.25$: $\beta \leftarrow \mathrm{clip}(\beta \cdot g_{\beta})$ | Else: $\beta \leftarrow \mathrm{clip}(\beta \cdot \rho)$ |
| **γ** | If γ active and $\delta_{\mathrm{worst}} > \varepsilon$: if $\gamma \approx 0$, seed $\gamma \leftarrow g_{\mathrm{seed}}$; else $\gamma \leftarrow \mathrm{clip}(\gamma \cdot g_{\gamma})$ | Else if $\delta_{\mathrm{worst}} < \varepsilon/2$: $\gamma \leftarrow \mathrm{clip}(\gamma \cdot \rho)$ |

This is a **heuristic outer loop** (not e.g. LQR or MPC): it trades off tracking, exhaustion sync, and FICO fairness by nudging weights when monitored quantities leave a **deadband**. **Stability or optimality of the joint inner–outer system is not claimed**—the intended use is **simulation and tuning** with explicit metrics and alerts.

---

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

Fields such as `alpha_min` / `alpha_max`, `beta_min` / `beta_max`, and `gamma_min` / `gamma_max` define min/max **clips** after each controller step so tuned weights stay in a safe range.

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
