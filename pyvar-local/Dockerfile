# pyvar-local/Dockerfile — offline, no-API-key pyvar compute engine
#
# Ships the exact same engine/ code that powers the hosted pyvar.com API --
# generated/packaged from the same source, not a fork. Built and published
# by a manually-triggered CodePipeline (pyvar-cdk/stacks/local_package_stack.py),
# never on every push. See pyvar-local/README.md for what this image does
# and deliberately doesn't (yet) do, and docs/proposals/pyvar-local-package-proposal.docx
# for the full rationale.
#
# Build context is the REPO ROOT (not this directory) -- see the COPY paths
# below, all relative to the root, matching how the CI/build pipeline
# actually invokes this: `docker build -f pyvar-local/Dockerfile .`
FROM python:3.11-slim

WORKDIR /app

# requirements-heavy.txt is pyvar's own compute-dependency list (numpy,
# numba, scipy, pandas, polars, pyarrow, statsmodels) -- reused verbatim
# rather than re-pinned here, so this image can't drift from what engine/
# actually needs.
COPY requirements-heavy.txt .
RUN pip install --no-cache-dir -r requirements-heavy.txt "pytest>=8.1.0"

COPY engine/ engine/
COPY tests/__init__.py tests/test_engine.py tests/
COPY pyvar-local/pyvar_local/ pyvar_local/

# Pre-warm the Numba JIT cache at build time, baking it into this image
# layer -- the same first-call-compilation problem CLAUDE.md's own known-
# issues section documents for the hosted worker fleet (fixed there by
# pre-baking an AMI), applied here to a container image instead.
RUN python -c "\
import numpy as np; \
from engine.montecarlo import run_monte_carlo_var; \
returns = np.random.default_rng(0).normal(0.0005, 0.012, 30); \
run_monte_carlo_var(returns, portfolio_value=1_000_000.0, confidence_level=0.99, horizon_days=1, n_simulations=1000, seed=1)"

ENTRYPOINT ["python", "-m", "pyvar_local.cli"]
CMD ["list"]
