"""Prove two independent workspaces keep isolated Sibyl memory.

Simulates visitor A and visitor B as separate HTTP clients with their own
workspace cookies against the same backend, then returns as A. Writes only
redacted identifiers to evidence/multi-user-isolation.json.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TMP = Path(tempfile.mkdtemp(prefix="prior-multiuser-"))
os.environ["PRIOR_DATA_DIR"] = str(TMP)
os.environ["PRIOR_MEMORY_DB"] = str(TMP / "sibyl-memory.db")
os.environ["ACP_ENABLED"] = "false"
os.environ["PRIOR_LOCAL_PROVIDER"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from prior.app import app  # noqa: E402

OUT = ROOT / "evidence" / "multi-user-isolation.json"


def ref(value: str) -> str:
    raw = value.removeprefix("ws_")
    short = raw if len(raw) <= 8 else f"{raw[:4]}...{raw[-4:]}"
    return f"ws: {short} (len {len(value)})"


def main() -> int:
    a = TestClient(app)
    ws_a = a.get("/api/workspace").json()["workspace_id"]
    job_a = a.post("/api/jobs", json={"text": "Research the top five AI wallet companies."}).json()
    assert job_a["contract"]["baseline"] is True
    hired_a = a.post(f"/api/jobs/{job_a['id']}/hire").json()
    assert hired_a["status"] == "delivered"
    a.post(
        f"/api/jobs/{job_a['id']}/reject",
        json={"reason": "Material factual claims must include identifiable source links."},
    )
    decided = a.post(f"/api/jobs/{job_a['id']}/lessons", json={"action": "add"}).json()
    assert decided["proposed_lesson"]["status"] == "active"
    mem_a = a.get("/api/memory").json()
    assert mem_a["count"] == 1

    b = TestClient(app)
    ws_b = b.get("/api/workspace").json()["workspace_id"]
    assert ws_b != ws_a
    job_b = b.post("/api/jobs", json={"text": "Research the top five AI wallet companies."}).json()
    mem_b = b.get("/api/memory").json()
    b_baseline = job_b["contract"]["baseline"] is True
    b_applied = len(job_b["contract"]["applied_lessons"]) == 0
    b_memory_empty = mem_b["lessons"] == [] and mem_b["count"] == 0

    a2 = TestClient(app)
    a2.cookies.set("prior_workspace", ws_a)
    same_workspace = a2.get("/api/workspace").json()["workspace_id"] == ws_a
    job_a2 = a2.post("/api/jobs", json={"text": "Research the top five decentralized exchanges."}).json()
    a2_recall = job_a2["contract"]["baseline"] is False
    a2_applied = len(job_a2["contract"]["applied_lessons"]) == 1
    hired_a2 = a2.post(f"/api/jobs/{job_a2['id']}/hire").json()
    worker_applied = decided["proposed_lesson"]["requirement"] in (
        hired_a2.get("worker_requirement", {}).get("learned_requirements", [])
    )

    evidence = {
        "pass": bool(
            b_baseline and b_applied and b_memory_empty and same_workspace and a2_recall and a2_applied and worker_applied
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace_a": ref(ws_a),
        "workspace_b": ref(ws_b),
        "workspaces_distinct": ws_b != ws_a,
        "user_a": {
            "job_1_baseline": True,
            "lesson_approved": True,
            "memory_count": 1,
            "returned_same_workspace": same_workspace,
            "job_2_baseline": False,
            "job_2_applied_lessons": 1,
            "worker_received_lesson": worker_applied,
        },
        "user_b": {
            "baseline_contract": b_baseline,
            "applied_lessons": 0,
            "memory_empty": b_memory_empty,
        },
        "note": "Identifiers are shortened. No cookies or secrets are stored.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
