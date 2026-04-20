"""
analytics_worker.py
===================

Compatibility subprocess entrypoint for RTLS analytics inference. This script
is intended to run under the project-local Python environment that matches the
model's original scikit-learn version.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from RTLSDashboard.analytics_runtime import _analyze_csv_log_local


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({
            "success": False,
            "error": "Usage: analytics_worker.py <csv_path>",
        }))
        return 2

    csv_path = sys.argv[1]
    try:
        result = _analyze_csv_log_local(csv_path)
    except Exception as exc:
        print(json.dumps({
            "success": False,
            "error": str(exc),
        }))
        return 1

    payload = {"success": True, **result}
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
