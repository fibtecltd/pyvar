"""pyvar-mcp: an MCP server for pyvar.com's risk functions."""

from importlib import metadata

try:
    __version__ = metadata.version("pyvar-mcp")
except metadata.PackageNotFoundError:  # a source tree that was never installed
    __version__ = "dev"
