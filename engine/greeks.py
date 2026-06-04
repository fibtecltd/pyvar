"""engine/greeks.py — Sensitivities / Greeks (Market Risk).

Portfolio-level aggregation Greeks (delta, gamma matrix, bucketed vega, bucketed
DV01/CS01) and Black-Scholes option Greeks (rho, theta, charm, volga, vanna).

Black-Scholes Greeks use closed-form expressions; aggregation Greeks are pure
NumPy reductions. No @njit is required here (the work is vectorised and light),
so CLAUDE.md §3.1 is satisfied trivially — there are no JIT kernels to constrain.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "portfolio_delta_aggregated",
    "gamma_cross_gamma_matrix",
    "vega_surface_bucketed",
]


def portfolio_delta_aggregated(
    deltas: np.ndarray,
    quantities: np.ndarray,
    spot_prices: np.ndarray | None = None,
) -> dict:  # type: ignore[type-arg]
    """Aggregate per-position deltas into a net portfolio delta.

    Net delta = Σ delta_i * quantity_i. When spot prices are supplied the
    cash (dollar) delta Σ delta_i * quantity_i * spot_i is also returned.

    Args:
        deltas: Per-position option delta (∂V/∂S).
        quantities: Signed position size per instrument.
        spot_prices: Optional underlying spot per position for cash delta.

    Returns:
        Dict with ``net_delta`` and (if spots given) ``cash_delta``.

    Raises:
        ValueError: If input lengths are inconsistent.
    """
    d = np.asarray(deltas, dtype=np.float64)
    q = np.asarray(quantities, dtype=np.float64)
    if d.size != q.size:
        raise ValueError("deltas and quantities must have the same length")

    net_delta = float(np.sum(d * q))
    result: dict = {"net_delta": round(net_delta, 8)}  # type: ignore[type-arg]
    if spot_prices is not None:
        s = np.asarray(spot_prices, dtype=np.float64)
        if s.size != d.size:
            raise ValueError("spot_prices must match deltas length")
        result["cash_delta"] = round(float(np.sum(d * q * s)), 4)
    return result


def gamma_cross_gamma_matrix(
    own_gammas: np.ndarray,
    cross_gammas: np.ndarray | None = None,
) -> dict:  # type: ignore[type-arg]
    """Assemble the portfolio gamma / cross-gamma matrix.

    The diagonal holds each underlying's net gamma (∂²V/∂S_i²); off-diagonals
    hold cross-gammas (∂²V/∂S_i∂S_j). The matrix is symmetric (Schwarz's
    theorem) — gamma P&L for a shock vector ds is ``0.5 · ds' G ds``.

    Args:
        own_gammas: Length-U net gamma per underlying (matrix diagonal).
        cross_gammas: Optional ``(U, U)`` cross-gamma matrix; its off-diagonal
            entries are symmetrised into the result. Diagonal is ignored.

    Returns:
        Dict with the symmetric ``gamma_matrix`` and ``is_symmetric`` flag.

    Raises:
        ValueError: If ``cross_gammas`` shape does not match ``own_gammas``.
    """
    g = np.asarray(own_gammas, dtype=np.float64)
    u = g.size
    matrix = np.diag(g).astype(np.float64)
    if cross_gammas is not None:
        cg = np.asarray(cross_gammas, dtype=np.float64)
        if cg.shape != (u, u):
            raise ValueError("cross_gammas must be (U, U) matching own_gammas")
        off = cg.copy()
        np.fill_diagonal(off, 0.0)
        sym_off = 0.5 * (off + off.T)  # enforce symmetry
        matrix = matrix + sym_off
    return {
        "gamma_matrix": matrix.tolist(),
        "is_symmetric": bool(np.allclose(matrix, matrix.T)),
    }


def vega_surface_bucketed(
    vegas: np.ndarray,
    expiry_buckets: np.ndarray,
    strike_buckets: np.ndarray,
    n_expiry: int,
    n_strike: int,
) -> dict:  # type: ignore[type-arg]
    """Aggregate option vegas onto a bucketed (expiry × strike) surface.

    Each option's vega is summed into its (expiry, strike) bucket. Total vega is
    conserved — the surface sum equals the input vega sum.

    Args:
        vegas: Per-option vega (∂V/∂σ).
        expiry_buckets: Per-option expiry bucket index in ``[0, n_expiry)``.
        strike_buckets: Per-option strike bucket index in ``[0, n_strike)``.
        n_expiry: Number of expiry buckets.
        n_strike: Number of strike buckets.

    Returns:
        Dict with the ``surface`` (n_expiry × n_strike) and ``total_vega``.

    Raises:
        ValueError: If lengths mismatch or bucket indices are out of range.
    """
    v = np.asarray(vegas, dtype=np.float64)
    ei = np.asarray(expiry_buckets, dtype=np.int64)
    si = np.asarray(strike_buckets, dtype=np.int64)
    if not (v.size == ei.size == si.size):
        raise ValueError("vegas, expiry_buckets, strike_buckets must be equal length")
    if v.size and (ei.min() < 0 or ei.max() >= n_expiry or si.min() < 0 or si.max() >= n_strike):
        raise ValueError("bucket index out of range")

    surface = np.zeros((n_expiry, n_strike), dtype=np.float64)
    for k in range(v.size):
        surface[ei[k], si[k]] += v[k]
    return {
        "surface": surface.tolist(),
        "total_vega": round(float(np.sum(surface)), 8),
    }
