"""Pulse construction public API.

This package exposes the high-level helpers most users need when working with
pulse generation:

- ``DefaultPulseLowering`` for converting ``CircuitIR`` into ``PulseIR``
- ``PulseCompiler`` for building pulse sequences
- ``build_gate_mapping_catalog`` for inspecting gate-to-pulse recipes
- ``instantiate_operation_recipe`` for resolving concrete pulse recipes
"""

from qsim.pulse.catalog import build_gate_mapping_catalog, instantiate_operation_recipe
from qsim.pulse.lowering import DefaultLowering, DefaultPulseLowering, IPulseLowering
from qsim.pulse.sequence import PulseCompiler

__all__ = [
    "DefaultLowering",
    "DefaultPulseLowering",
    "IPulseLowering",
    "PulseCompiler",
    "build_gate_mapping_catalog",
    "instantiate_operation_recipe",
]
