#!/usr/bin/env python3
"""fix-p2-branches.py — targeted ruff/mypy fixes across all 4 P2 branches."""
import pathlib, re

BASE = pathlib.Path.home() / "projects/pyvar-worktrees"

def patch(path, old, new, label):
    src = path.read_text()
    if old not in src:
        print(f"  SKIP (not found): {label}"); return False
    path.write_text(src.replace(old, new, 1))
    print(f"  FIXED: {label}"); return True

def patch_re(path, pattern, repl, label):
    src = path.read_text()
    new_src, n = re.subn(pattern, repl, src)
    if n == 0:
        print(f"  SKIP (no match): {label}"); return False
    path.write_text(new_src)
    print(f"  FIXED ({n}x): {label}"); return True

# ── CREDIT-RISK ───────────────────────────────────────────────────────────────
print("\n── credit-risk ──")

# E741: credit_pd_lgd.py — rename l → lgd_arr
p = BASE / "credit-risk/engine/credit_pd_lgd.py"
src = p.read_text()
new = re.sub(r'\bl\b', 'lgd_arr', src)
if new != src: p.write_text(new); print("  FIXED: credit_pd_lgd.py l→lgd_arr")
else: print("  SKIP: credit_pd_lgd.py")

# E741: credit_var.py — rename l → lgd_arr
p = BASE / "credit-risk/engine/credit_var.py"
src = p.read_text()
new = re.sub(r'\bl\b', 'lgd_arr', src)
if new != src: p.write_text(new); print("  FIXED: credit_var.py l→lgd_arr")
else: print("  SKIP: credit_var.py")

# mypy: credit_var.py — float(asset_correlation) → np.float64
patch(BASE/"credit-risk/engine/credit_var.py",
    "rho = np.full(n, float(asset_correlation), dtype=np.float64)",
    "rho = np.full(n, np.float64(asset_correlation), dtype=np.float64)",
    "credit_var.py — np.float64 cast")

# mypy: credit_capital.py — wrap returns in float()
p = BASE / "credit-risk/engine/credit_capital.py"
patch(p, "    return 0.12 * w + 0.24 * (1.0 - w)",
         "    return float(0.12 * w + 0.24 * (1.0 - w))",
         "credit_capital.py:53")
patch(p, "    return val * val",
         "    return float(val * val)",
         "credit_capital.py:60")

# ── LIQUIDITY-OPS ─────────────────────────────────────────────────────────────
print("\n── liquidity-ops ──")

p = BASE / "liquidity-ops/engine/liquidity_stress.py"
patch(p, "    return balances * runoff_rates",
         "    return np.asarray(balances * runoff_rates, dtype=np.float64)",
         "liquidity_stress.py:56 — ndarray cast")
patch(p, "    scenarios: dict,",
         "    scenarios: dict[str, Any],",
         "liquidity_stress.py:360 — dict[str,Any]")
# Ensure Any is imported
src = p.read_text()
if "from typing import Any" not in src:
    src = src.replace("import numpy as np", "import numpy as np\nfrom typing import Any", 1)
    p.write_text(src); print("  FIXED: liquidity_stress.py — Any import")

# ── PORTFOLIO-REG ─────────────────────────────────────────────────────────────
print("\n── portfolio-reg ──")

p = BASE / "portfolio-reg/engine/portfolio_optimisation.py"
patch(p, "        return -(w @ mu - 0.5 * risk_aversion * (w @ cov @ w))",
         "        return float(-(w @ mu - 0.5 * risk_aversion * (w @ cov @ w)))",
         "portfolio_optimisation.py:132")
patch(p, "        return -(w @ worst_mu - 0.5 * risk_aversion * (w @ cov @ w))",
         "        return float(-(w @ worst_mu - 0.5 * risk_aversion * (w @ cov @ w)))",
         "portfolio_optimisation.py:463")

# ── DRV-ALM ───────────────────────────────────────────────────────────────────
print("\n── drv-alm ──")

# E741: alm_ftp.py:228 — rename loop var l → lb
p = BASE / "drv-alm/engine/alm_ftp.py"
patch(p, '"liabilities": [round(float(l), 4) for l in liabs],',
         '"liabilities": [round(float(lb), 4) for lb in liabs],',
         "alm_ftp.py:228 — l→lb in list comp")

# E741: alm_irrbb.py — rename l → liab in all 3 functions
p = BASE / "drv-alm/engine/alm_irrbb.py"
src = p.read_text()
# Replace l = np.asarray(bucket_liabilities...) and all uses within those functions
new = src
new = new.replace(
    "    l = np.asarray(bucket_liabilities, dtype=np.float64)\n    if a.size != l.size:",
    "    liab = np.asarray(bucket_liabilities, dtype=np.float64)\n    if a.size != liab.size:")
new = new.replace("    gap = a - l\n", "    gap = a - liab\n")
new = new.replace("    total_l = float(np.sum(l))", "    total_liab = float(np.sum(liab))")
new = new.replace("    if not (a.size == l.size == ag.size == lg.size):",
                  "    if not (a.size == liab.size == ag.size == lg.size):")
if new != src: p.write_text(new); print("  FIXED: alm_irrbb.py l→liab (3 functions)")
else: print("  SKIP: alm_irrbb.py")

# F841: deriv_options_exotic.py:139 — prefix unused lam with _
p = BASE / "drv-alm/engine/deriv_options_exotic.py"
patch(p, "    lam = math.sqrt(mu * mu + 2.0 * rate / (sigma * sigma))",
         "    _lam = math.sqrt(mu * mu + 2.0 * rate / (sigma * sigma))",
         "deriv_options_exotic.py:139 — _lam")

# mypy: deriv_options_exotic.py:255,592 — njit return → np.asarray
p = BASE / "drv-alm/engine/deriv_options_exotic.py"
patch(p, "    return _gbm_path_stats(spot, rate, div_yield, sigma, tau, normals)",
         "    return np.asarray(_gbm_path_stats(spot, rate, div_yield, sigma, tau, normals))",
         "deriv_options_exotic.py:255")
patch(p, "    return _multi_asset_terminals(spots, rate, sigmas, tau, chol, normals)",
         "    return np.asarray(_multi_asset_terminals(spots, rate, sigmas, tau, chol, normals))",
         "deriv_options_exotic.py:592")

# F841 + mypy: deriv_options_vanilla.py:126 — prefix d with _, wrap returns
p = BASE / "drv-alm/engine/deriv_options_vanilla.py"
patch(p, "    d = 1.0 / u\n", "    _d = 1.0 / u\n", "deriv_options_vanilla.py:126 — _d")
# Return values[0] appears in both _binomial (line 107) and _trinomial (line 159)
src = p.read_text()
new = src.replace("    return values[0]\n", "    return float(values[0])\n")
if new != src: p.write_text(new); print("  FIXED: deriv_options_vanilla.py — float(values[0])")
else: print("  SKIP: deriv_options_vanilla.py returns")

# mypy: deriv_bonds.py:230 — return values[0] as float
p = BASE / "drv-alm/engine/deriv_bonds.py"
patch(p, "    return values[0]\n", "    return float(values[0])\n", "deriv_bonds.py:230")

# mypy: deriv_stoch_vol.py:58 — return complex
p = BASE / "drv-alm/engine/deriv_stoch_vol.py"
patch(p,
    "    return np.exp(c_term + d_term * v0 + 1j * u * np.log(spot))",
    "    return complex(np.exp(c_term + d_term * v0 + 1j * u * np.log(spot)))",
    "deriv_stoch_vol.py:58")

# mypy: deriv_bond_analytics.py:402 — return float(p) - market_price
p = BASE / "drv-alm/engine/deriv_bond_analytics.py"
patch(p, "        return p - market_price", "        return float(p) - market_price",
      "deriv_bond_analytics.py:402")

# mypy: deriv_rates.py:194 — type annotation + np.array([1.0])
p = BASE / "drv-alm/engine/deriv_rates.py"
patch(p,
    "    surv_prev = np.concatenate(([1.0], surv[:-1]))",
    "    surv_prev: np.ndarray = np.concatenate((np.array([1.0], dtype=np.float64), surv[:-1]))",
    "deriv_rates.py:194 — annotation + array cast")

print("\nAll fixes applied. Run: git add -A && git commit on each worktree.")
