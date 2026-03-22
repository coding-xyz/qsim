"""Pulse construction public API.

This package exposes the high-level helpers most users need when working with
pulse generation:

- ``PulseCompiler`` for building pulse sequences
- ``build_gate_mapping_catalog`` for inspecting gate-to-pulse recipes
- ``instantiate_operation_recipe`` for resolving concrete pulse recipes
"""

from qsim.pulse.catalog import build_gate_mapping_catalog, instantiate_operation_recipe
from qsim.pulse.sequence import PulseCompiler

__all__ = ["PulseCompiler", "build_gate_mapping_catalog", "instantiate_operation_recipe"]
