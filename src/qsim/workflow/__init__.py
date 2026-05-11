"""Workflow public API."""

from qsim.workflow.contracts import (
    DefaultAnalyserConfig,
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
from qsim.schemas.results import ModelAnalysis
from qsim.workflow.model import Model, create_model, load_model
from qsim.workflow.planner import ExecutionPlan, build_execution_plan
from qsim.workflow.session_adapter import commit_result_to_session
from qsim.workflow.task_io import (
    load_config_bundle_files,
    load_analyser_config_file,
    load_device_config_file,
    load_pulse_config_file,
    load_solver_config_file,
    load_task_config_file,
    load_task_file,
)

__all__ = [
    "SolverBackendConfig",
    "DefaultAnalyserConfig",
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
    "ModelAnalysis",
    "Model",
    "create_model",
    "load_model",
    "ExecutionPlan",
    "build_execution_plan",
    "commit_result_to_session",
    "load_config_bundle_files",
    "load_analyser_config_file",
    "load_device_config_file",
    "load_pulse_config_file",
    "load_solver_config_file",
    "load_task_config_file",
    "load_task_file",
]

# Deprecated compatibility alias. Prefer ``ModelAnalysis`` in new code.
AnalysisResult = ModelAnalysis
__all__.append("AnalysisResult")
