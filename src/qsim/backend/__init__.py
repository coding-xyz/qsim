"""Backend compilation public API.

The backend package is responsible for converting normalized circuits into
model specifications and executable artifacts. The most common public entry
points are ``CompilePipeline`` and ``load_backend_config``.
"""

from qsim.backend.compile_pipeline import CompilePipeline
from qsim.backend.config import load_backend_config

__all__ = ["CompilePipeline", "load_backend_config"]
