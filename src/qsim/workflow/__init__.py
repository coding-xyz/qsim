"""Workflow public API.

This package contains the main entrypoints used by the documentation and CLI:

- workflow dataclasses such as ``WorkflowTask`` and ``WorkflowRunOptions``
- config-file loaders for task / solver / device / pulse inputs
- execution planning helpers
- ``run_task`` and ``run_task_files`` for launching workflows
- session commit helpers for persisting selected outputs
"""

from qsim.workflow.contracts import (
    SolverBackendConfig,
    TaskInputConfig,
    WorkflowDeviceConfig,
    WorkflowFeatureFlags,
    WorkflowFrameOptions,
    WorkflowInput,
    WorkflowOutputOptions,
    WorkflowRunOptions,
    WorkflowSolverConfig,
    WorkflowTask,
    WorkflowTaskConfig,
    compose_workflow_task,
    normalize_device_payload,
)
from qsim.workflow.planner import ExecutionPlan, build_execution_plan
from qsim.workflow.pipeline import run_task, run_task_files
from qsim.workflow.session_adapter import commit_result_to_session
from qsim.workflow.task_io import (
    load_config_bundle_files,
    load_device_config_file,
    load_pulse_config_file,
    load_solver_config_file,
    load_task_config_file,
    load_task_file,
)

__all__ = [
    "SolverBackendConfig",
    "TaskInputConfig",
    "WorkflowFeatureFlags",
    "WorkflowFrameOptions",
    "WorkflowDeviceConfig",
    "WorkflowInput",
    "WorkflowOutputOptions",
    "WorkflowRunOptions",
    "WorkflowSolverConfig",
    "WorkflowTask",
    "WorkflowTaskConfig",
    "compose_workflow_task",
    "normalize_device_payload",
    "ExecutionPlan",
    "build_execution_plan",
    "commit_result_to_session",
    "load_config_bundle_files",
    "load_device_config_file",
    "load_pulse_config_file",
    "load_solver_config_file",
    "load_task_config_file",
    "load_task_file",
    "run_task",
    "run_task_files",
]
