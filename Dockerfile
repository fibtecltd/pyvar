# ============================================================
# Dockerfile  —  pyvar API production image
# Location   :  ~/projects/pyvar/Dockerfile
#
# This Dockerfile is ONLY for the pyvar application.
# Claude Code lives in a separate Dockerfile in ~/claude-docker/.
#
# Two build stages:
#   builder   Compiles all Python deps + Numba JIT cache.
#             Build tools present here, stripped in runtime.
#   runtime   Lean production image. Used by:
#               ECS Fargate  — FastAPI API service
#               EC2 Spot ASG — Celery compute workers
#
# Build:
#   docker build --target runtime -t pyvar-api .
#   docker compose build pyvar-api   (via pyvar/docker-compose.yml)
# ============================================================

FROM python:3.11-slim AS builder

WORKDIR /build

# Build dependencies
# gcc / g++      — asyncpg, psycopg2, llvmlite (Numba)
# libpq-dev      — PostgreSQL headers
# liblz4-dev     — PyArrow LZ4 Parquet codec (required at compile time)
# libsnappy-dev  — PyArrow Snappy Parquet codec
# libzstd-dev    — PyArrow / Polars Zstandard codec
# libssl-dev     — Ray TLS, boto3
# curl           — download utility
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    liblz4-dev \
    libsnappy-dev \
    libzstd-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip once — prevents dependency resolution failures
RUN pip install --upgrade pip setuptools wheel

# ── Heavy packages: own layer ────────────────────────────────
# Numba, Ray, SciPy, QuantLib take 10-15 min to compile.
# Separated so adding a lightweight package to requirements.txt
# does NOT invalidate this expensive layer.
COPY requirements-heavy.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements-heavy.txt

# ── Application packages ─────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Pre-compile Numba JIT cache ──────────────────────────────
# Compiles the Monte Carlo kernel at build time.
# Without this, the first API request pays ~2s LLVM compilation.
# If engine/montecarlo.py @njit signature changes, rebuild
# with --no-cache to regenerate the compiled cache.
COPY engine/ /build/engine/
# PYTHONPATH must include both locations:
#   /install/lib/python3.11/site-packages  — numpy/numba installed via --prefix=/install
#   /build                                 — engine/montecarlo.py source
# Without /install/lib/..., Python cannot find numpy even though it was
# successfully installed in the previous RUN step.
RUN NUMBA_CACHE_DIR=/root/.cache/numba \
    PYTHONPATH=/install/lib/python3.11/site-packages:/build \
    python3 -c "\
import numpy as np; \
import sys; \
sys.path.insert(0, '/build'); \
from engine.montecarlo import run_monte_carlo_var; \
dummy = np.random.randn(60) * 0.01; \
run_monte_carlo_var(dummy, portfolio_value=1.0, n_simulations=100, seed=0); \
print('Numba warmup complete')"


# ── Runtime stage ─────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime system deps only (no build tools)
# libpq5   — asyncpg PostgreSQL driver
# curl     — ECS / ALB health check probe
# liblz4-1 — PyArrow LZ4 Parquet codec runtime
# libzstd1 — PyArrow / Polars Zstandard Parquet codec runtime
#
# libsnappy1 intentionally excluded:
#   Package was removed / renamed in Debian Bookworm and has no
#   installation candidate. Snappy Parquet codec is therefore
#   unavailable at runtime — PyArrow degrades gracefully (no crash).
#   Ensure Parquet writes in the application use 'lz4' or 'zstd':
#     pq.write_table(table, path, compression='lz4')
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    liblz4-1 \
    libzstd1 \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built Python packages from builder (no build tools)
COPY --from=builder /install /usr/local

# Copy pre-compiled Numba cache from builder
COPY --from=builder /root/.cache/numba/ /home/pyvar/.cache/numba/

# Copy application source
COPY . .

# Non-root user
# Combined chown covers /app and Numba cache in one RUN layer
RUN useradd -m -u 1001 pyvar \
    && chown -R pyvar:pyvar /app /home/pyvar/.cache

USER pyvar

# Expose API port
EXPOSE 8000

# Health check — aligns with ECS task definition startPeriod=30s
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Point Numba to the pre-compiled cache for the non-root user.
# Without this env var the non-root pyvar user will not find the
# cache baked in at /home/pyvar/.cache/numba and will recompile
# on every cold start — wasting the warmup done in the builder stage.
ENV NUMBA_CACHE_DIR=/home/pyvar/.cache/numba
ENV PYTHONUNBUFFERED=1

# Start uvicorn
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--no-access-log"]
