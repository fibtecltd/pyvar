"""Shim: this module moved to assistant/graders.py; the name here is the same module object.

Kept so every script, test and import that says `graders` (or `scripts.assistant_eval.graders`) still works, and so a
monkeypatch through either name is seen through both. See tests/test_assistant_core.py.
"""

import importlib
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
sys.modules[__name__] = importlib.import_module("assistant.graders")
