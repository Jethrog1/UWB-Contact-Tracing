#!/usr/bin/env python3
"""
BRIGID backend setup helper.

This script is intentionally safe to run multiple times. It prepares optional
runtime pieces that should not block the rest of the app if they are missing.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent
MODEL_BUNDLE_PATH = PROJECT_ROOT / "assets" / "ML" / "final_model_bundle.pkl"
ML_COMPAT_ENV = BACKEND_ROOT / ".conda-ml-compat"
ML_COMPAT_PYTHON = (
    ML_COMPAT_ENV / "Scripts" / "python.exe"
    if os.name == "nt"
    else ML_COMPAT_ENV / "bin" / "python"
)
ML_COMPAT_SPEC = {
    "python": "3.11",
    "scikit_learn": "1.2.2",
    "numpy": "1.26.4",
    "scipy": "1.11.4",
    "pandas": "2.2.3",
    "joblib": "1.5.3",
}


def _log(message: str) -> None:
    print(f"[setup] {message}")


def _run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )


def _find_conda() -> str | None:
    return os.environ.get("CONDA_EXE") or shutil.which("conda")


def _read_ml_versions() -> dict[str, str] | None:
    if not ML_COMPAT_PYTHON.exists():
        return None
    try:
        completed = _run([
            str(ML_COMPAT_PYTHON),
            "-c",
            (
                "import json, joblib, numpy, pandas, scipy, sklearn; "
                "print(json.dumps({"
                "'python': '.'.join(map(str, __import__(\"sys\").version_info[:2])), "
                "'scikit_learn': sklearn.__version__, "
                "'numpy': numpy.__version__, "
                "'scipy': scipy.__version__, "
                "'pandas': pandas.__version__, "
                "'joblib': joblib.__version__"
                "}))"
            ),
        ])
        return json.loads(completed.stdout.strip())
    except Exception:
        return None


def _matches_ml_spec(versions: dict[str, str] | None) -> bool:
    if not versions:
        return False
    return all(str(versions.get(key)) == expected for key, expected in ML_COMPAT_SPEC.items())


def ensure_ml_compat() -> int:
    if not MODEL_BUNDLE_PATH.exists():
        _log("No bundled RTLS analytics model detected.")
        return 0

    current_versions = _read_ml_versions()
    if _matches_ml_spec(current_versions):
        _log("ML compatibility runtime already matches the bundled RTLS model.")
        return 0

    conda_exe = _find_conda()
    if not conda_exe:
        _log("Conda was not found, but the bundled RTLS analytics model requires a pinned Python 3.11 / scikit-learn 1.2.2 runtime.")
        _log("Install Conda (or Miniconda) and rerun setup so BRIGID can provision backend/.conda-ml-compat.")
        return 1

    try:
        if not ML_COMPAT_PYTHON.exists():
            _log("Creating RTLS analytics compatibility runtime...")
            _run([conda_exe, "create", "-p", str(ML_COMPAT_ENV), f"python={ML_COMPAT_SPEC['python']}", "pip", "-y"])

        _log("Installing pinned RTLS analytics dependencies into compatibility runtime...")
        _run([
            str(ML_COMPAT_PYTHON),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--force-reinstall",
            f"numpy=={ML_COMPAT_SPEC['numpy']}",
            f"scipy=={ML_COMPAT_SPEC['scipy']}",
            f"scikit-learn=={ML_COMPAT_SPEC['scikit_learn']}",
            f"pandas=={ML_COMPAT_SPEC['pandas']}",
            f"joblib=={ML_COMPAT_SPEC['joblib']}",
        ])
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            _log(exc.stdout.strip())
        if exc.stderr:
            _log(exc.stderr.strip())
        _log("ML compatibility runtime setup failed.")
        return 1

    final_versions = _read_ml_versions()
    if _matches_ml_spec(final_versions):
        _log("RTLS analytics compatibility runtime is ready.")
        return 0

    _log("ML compatibility runtime did not verify cleanly.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare optional BRIGID backend runtime components.")
    parser.add_argument(
        "--ensure-ml-compat",
        action="store_true",
        help="Prepare the project-local compatibility runtime required by the bundled RTLS analytics model.",
    )
    args = parser.parse_args()

    if args.ensure_ml_compat:
        return ensure_ml_compat()

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
