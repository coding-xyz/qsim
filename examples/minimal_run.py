from pathlib import Path

from qsim.workflow import WorkflowInput, WorkflowRunOptions, WorkflowTask, run_task


if __name__ == "__main__":
    qasm_text = Path("examples/bell.qasm").read_text(encoding="utf-8")
    result = run_task(
        WorkflowTask(
            input=WorkflowInput(
                qasm_text=qasm_text,
                backend_path="examples/backend.yaml",
                out_dir="runs/minimal",
            ),
            run=WorkflowRunOptions(engine="qutip"),
        )
    )
    print("Done:", result["runtime"]["out_dir"])
