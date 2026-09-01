"""Run the Sibyl cross-process kill-test as two separate Python processes."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
A = ROOT / "scripts" / "sibyl_kill_test_a.py"
B = ROOT / "scripts" / "sibyl_kill_test_b.py"
OUT = ROOT / "evidence" / "sibyl-kill-test.json"


def run(script: Path) -> dict:
    proc = subprocess.run(
        [PY, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"{script.name} failed ({proc.returncode})\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def main() -> int:
    a = run(A)
    b = run(B)
    summary = {
        "pass": bool(a.get("ok") and b.get("ok")),
        "process_a": a,
        "process_b": b,
    }
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
