"""Workflow contracts, loaders, and task execution API."""

from qsim.workflow.contracts import (
    SolverBackendConfig,
    TaskInputConfig,
    WorkflowFeatureFlags,
    WorkflowHardwareConfig,
    WorkflowInput,
    WorkflowOutputOptions,
    WorkflowRunOptions,
    WorkflowSolverConfig,
    WorkflowTask,
    WorkflowTaskConfig,
    compose_workflow_task,
)
from qsim.workflow.planner import ExecutionPlan, build_execution_plan
from qsim.workflow.pipeline import run_task, run_task_files
from qsim.workflow.session_adapter import commit_result_to_session
from qsim.workflow.task_io import (
    load_config_bundle_files,
    load_hardware_config_file,
    load_solver_config_file,
    load_task_config_file,
    load_task_file,
)

__all__ = [
    "SolverBackendConfig",
    "TaskInputConfig",
    "WorkflowFeatureFlags",
    "WorkflowHardwareConfig",
    "WorkflowInput",
    "WorkflowOutputOptions",
    "WorkflowRunOptions",
    "WorkflowSolverConfig",
    "WorkflowTask",
    "WorkflowTaskConfig",
    "compose_workflow_task",
    "ExecutionPlan",
    "build_execution_plan",
    "commit_result_to_session",
    "load_config_bundle_files",
    "load_hardware_config_file",
    "load_solver_config_file",
    "load_task_config_file",
    "load_task_file",
    "run_task",
    "run_task_files",
]
