"""Cold-start proof through PRIOR, not a raw SDK demo.

Process A writes an approved lesson via Sibyl.
Process B is a new Python process that specifies a new job and must
mutate the contract from that lesson.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
DB = ROOT / "data" / "fresh-session.db"
OUT = ROOT / "evidence" / "fresh-session-prior.json"


WRITE = r"""
import json, os, sys
os.environ["PRIOR_MEMORY_DB"] = sys.argv[1]
from prior.domain import Lesson
from prior.lessons import now_iso
from prior.memory import write_lesson
lesson = Lesson(
    id="L_fresh_prior",
    workspace_id="ws_fresh_prior",
    job_type="research",
    issue="Unsupported factual claims",
    requirement="Material factual claims must include identifiable source links.",
    reason="Approved in process A.",
    status="active",
    provenance="user-approved",
    created_at=now_iso(),
    domains=["decentralized exchanges"],
    keywords=["exchanges", "sources", "research"],
    source_job_id="job_fresh_a",
)
write_lesson("ws_fresh_prior", lesson)
print(json.dumps({"ok": True, "pid": os.getpid(), "lesson_id": lesson.id}))
"""

READ = r"""
import json, os, sys
os.environ["PRIOR_MEMORY_DB"] = sys.argv[1]
from prior.service import specify
job = specify("ws_fresh_prior", "Research the top five decentralized exchanges.")
print(json.dumps({
    "ok": True,
    "pid": os.getpid(),
    "baseline": job.contract.baseline,
    "acceptance": job.contract.acceptance,
    "applied": [l.to_dict() for l in job.contract.applied_lessons],
    "memory_status": job.contract.memory_status,
}))
"""


def main() -> int:
    if DB.exists():
        DB.unlink()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    a = subprocess.run([PY, "-c", WRITE, str(DB)], cwd=str(ROOT), capture_output=True, text=True, check=False, env=env)
    if a.returncode != 0:
        print(a.stderr)
        return 1
    b = subprocess.run([PY, "-c", READ, str(DB)], cwd=str(ROOT), capture_output=True, text=True, check=False, env=env)
    if b.returncode != 0:
        print(b.stderr)
        return 1
    write = json.loads(a.stdout)
    read = json.loads(b.stdout)
    changed = any("source" in item.lower() for item in read.get("acceptance") or [])
    summary = {
        "pass": bool(
            write.get("ok")
            and read.get("ok")
            and write["pid"] != read["pid"]
            and read.get("baseline") is False
            and changed
        ),
        "process_a": write,
        "process_b": read,
        "contract_changed": changed,
    }
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
