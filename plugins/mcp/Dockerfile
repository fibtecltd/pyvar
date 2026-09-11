# plugins/mcp/Dockerfile — pyvar-mcp, containerised for hosted MCP registries
# (Smithery's "container" runtime; see smithery.yaml in this directory)
#
# Same base-image convention as pyvar-local/Dockerfile (python:3.11-slim),
# but far lighter: pyvar-mcp is a thin REST client over the live pyvar API
# (README.md's own words) -- its only real runtime dependencies are `mcp`
# and `anyio` (pyproject.toml), not the numpy/numba/scipy compute stack
# pyvar-local bundles. Self-contained: pyvar_mcp/_generated/functions.py is
# a flat, committed file (generated from portal/functions.json at repo-build
# time, see scripts/generate_mcp_tools.py) -- nothing outside this directory
# is needed at runtime, so this directory alone is the build context.
#
# Build (from this directory):
#   docker build -t pyvar-mcp .
# Run (stdio transport -- Smithery's container runtime talks to this over
# stdin/stdout, matching the plugin's own mcpServers config in
# .claude-plugin/plugin.json):
#   docker run -i --rm -e PYVAR_API_KEY=<key> pyvar-mcp
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY pyvar_mcp/ pyvar_mcp/

RUN pip install --no-cache-dir .

ENTRYPOINT ["pyvar-mcp"]
