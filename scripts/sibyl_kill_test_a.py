"""Process A: write a real Sibyl lesson, then exit."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sibyl_memory_client import MemoryClient

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "sibyl-kill-test.db"
EVIDENCE = ROOT / "evidence" / "sibyl-kill-test-a.json"
TENANT = "ws_killtest_alice"
OTHER_TENANT = "ws_killtest_bob"
LESSON_NAME = "L_killtest_sources"


def main() -> int:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    for suffix in ("-wal", "-shm", "-journal"):
        extra = Path(str(DB) + suffix)
        if extra.exists():
            extra.unlink()

    client = MemoryClient.local(DB, tenant_id=TENANT)
    body = {
        "id": LESSON_NAME,
        "workspace_id": TENANT,
        "job_type": "research",
        "issue": "Unsupported factual claims",
        "requirement": "Material factual claims must include identifiable source links.",
        "reason": "Kill-test seed written by process A.",
        "source_job_id": "job_killtest_1",
        "status": "active",
        "provenance": "kill-test",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "domains": ["decentralized exchanges"],
        "keywords": ["research", "sources", "citations"],
        "originating_evaluation": "rejected",
    }
    written = client.set_entity("lesson", LESSON_NAME, body)
    event_id = client.write_event(
        acted=["kill-test wrote lesson"],
        extra={"lesson_id": LESSON_NAME, "workspace_id": TENANT},
    )

    other = MemoryClient.local(DB, tenant_id=OTHER_TENANT)
    other.set_entity(
        "lesson",
        "L_killtest_bob_only",
        {
            "id": "L_killtest_bob_only",
            "workspace_id": OTHER_TENANT,
            "requirement": "Bob-only rule that Alice must never see.",
            "status": "active",
            "job_type": "research",
        },
    )

    recalled = client.get_entity("lesson", LESSON_NAME)
    payload = {
        "db": "data/sibyl-kill-test.db",
        "tenant": client.get_tenant(),
        "lesson_name": LESSON_NAME,
        "written_id": written.get("id"),
        "event_id": event_id,
        "requirement": recalled["body"]["requirement"],
        "workspace_id": recalled["body"]["workspace_id"],
        "pid": os_getpid(),
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "evidence": "evidence/sibyl-kill-test-a.json", "pid": payload["pid"]}))
    return 0


def os_getpid() -> int:
    import os

    return os.getpid()


if __name__ == "__main__":
    sys.exit(main())
