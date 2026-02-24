from pathlib import Path

from qsim.ui.notebook import run_workflow


if __name__ == "__main__":
    qasm_text = Path("examples/bell.qasm").read_text(encoding="utf-8")
    result = run_workflow(
        qasm_text=qasm_text,
        backend_path="examples/backend.yaml",
        out_dir="runs/minimal",
        engine="qutip",
    )
    print("Done:", result["out_dir"])
