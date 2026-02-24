from __future__ import annotations

from qsim.common.schemas import PulseIR
from qsim.pulse.sequence import PulseCompiler


compile_pulse_ir = PulseCompiler.compile
save_pulse_samples = PulseCompiler.to_npz
