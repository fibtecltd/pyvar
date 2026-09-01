"""pyvar_jupyter -- %pyvar / %%pyvar magics and rich display for pyvar.com in Jupyter.

>>> %load_ext pyvar_jupyter
>>> %pyvar_key eyJ...
>>> %pyvar market_risk.monte_carlo_var returns=[0.01,-0.02,0.015] portfolio_value=1000000

See README.md for the full magic syntax and the display helper, and
examples/ for worked notebooks.
"""

from __future__ import annotations

from pyvar_jupyter._display import PyvarResult, show
from pyvar_jupyter._magics import PyvarMagics

__version__ = "0.1.0"

__all__ = ["PyvarMagics", "PyvarResult", "show", "__version__", "load_ipython_extension"]


def load_ipython_extension(ipython) -> None:
    """Called by IPython on `%load_ext pyvar_jupyter` -- registers the magics."""
    ipython.register_magics(PyvarMagics)


def unload_ipython_extension(ipython) -> None:
    """IPython calls this on %unload_ext, if ever needed. No teardown required --
    register_magics has no matching unregister; the class instance is just
    dropped when the extension is unloaded."""
