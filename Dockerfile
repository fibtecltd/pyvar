# pyvar API — production Dockerfile
#
# Multi-stage build:
#   Stage 1 (builder): installs all deps including build tools
#   Stage 2 (runtime): copies only the installed packages — no build tools in prod
#
# Reasoning:
# - Multi-stage keeps the final image small (~400MB vs ~900MB single-stage).
# - Numba requires LLVM at build time but NOT at runtime (compiled cache is portable).
# - Non-root user (pyvar) follows container security best practices.
# - Numba compiled cache is pre-populated at build time via a warmup run.

FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Pre-compile Numba JIT cache during image build
# This means the first request after container start doesn't pay compilation cost
COPY engine/ /build/engine/
RUN python3 -c "
import numpy as np
import sys
sys.path.insert(0, '/build')
from engine.montecarlo import run_monte_carlo_var
dummy = np.random.randn(60) * 0.01
run_monte_carlo_var(dummy, portfolio_value=1.0, n_simulations=100, seed=0)
print('Numba warmup complete')
"

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime system deps only (libpq for asyncpg, curl for health check)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy pre-compiled Numba cache from builder
COPY --from=builder /root/.cache/numba/ /home/pyvar/.cache/numba/

# Copy application source
COPY . .

# Non-root user
RUN useradd -m -u 1001 pyvar \
    && chown -R pyvar:pyvar /app /home/pyvar/.cache

USER pyvar

# Expose API port
EXPOSE 8000

# Health check — used by ECS to determine task readiness
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start uvicorn
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--no-access-log"]
