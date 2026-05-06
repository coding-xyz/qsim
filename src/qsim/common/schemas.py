"""Compatibility exports for legacy ``qsim.common.schemas`` imports.

New code should import IR/spec dataclasses from ``qsim.schemas`` or its grouped
submodules. This module remains as a stable facade for existing callers.
"""

from qsim.schemas import *
