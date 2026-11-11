"""The portal assistant's shared kernel: the prompts, graders and helpers the measurements used.

The eval harness (scripts/assistant_eval/) measured these exact modules; production code imports them from here so
that what ships is what was measured. Nothing in this package may import a network or HTTP library: the one
module allowed to reach the model provider is added by a later change (see tests/test_assistant_core.py). The old
paths under scripts/assistant_eval/ are thin shims that resolve to the same module objects.
"""
