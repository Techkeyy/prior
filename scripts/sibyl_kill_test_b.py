"""Process B: fresh process, recall the lesson, apply it to a contract."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from sibyl_memory_client import MemoryClient, NotFoundError

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "sibyl-kill-test.db"
EVIDENCE_A = ROOT / "evidence" / "sibyl-kill-test-a.json"
EVIDENCE_B = ROOT / "evidence" / "sibyl-kill-test-b.json"
TENANT = "ws_killtest_alice"
OTHER_TENANT = "ws_killtest_bob"
LESSON_NAME = "L_killtest_sources"


def main() -> int:
    if not DB.exists():
        print(json.dumps({"ok": False, "error": "database missing; process A did not persist"}))
        return 1

    client = MemoryClient.local(DB, tenant_id=TENANT)
    entity = client.get_entity("lesson", LESSON_NAME)
    body = entity["body"]
    hits = client.search_entities("source links", category="lesson", limit=10)
    hit_names = [row["name"] for row in hits]

    leaked = False
    leak_error = None
    try:
        client.get_entity("lesson", "L_killtest_bob_only")
        leaked = True
    except NotFoundError as exc:
        leak_error = str(exc)

    other = MemoryClient.local(DB, tenant_id=OTHER_TENANT)
    bob = other.get_entity("lesson", "L_killtest_bob_only")

    baseline = [
        "Cover the requested subjects.",
        "Include names, products, pricing, strengths, and weaknesses.",
    ]
    applied = list(baseline)
    if body.get("status") == "active":
        applied.append(body["requirement"])

    evidence = {
        "pid": os.getpid(),
        "db": "data/sibyl-kill-test.db",
        "tenant": client.get_tenant(),
        "recalled_name": entity["name"],
        "recalled_requirement": body["requirement"],
        "recalled_workspace": body["workspace_id"],
        "search_hit_names": hit_names,
        "alice_cannot_read_bob": (not leaked),
        "alice_leak_error": leak_error,
        "bob_requirement": bob["body"]["requirement"],
        "baseline_acceptance": baseline,
        "memory_mutated_acceptance": applied,
        "contract_changed": applied != baseline,
        "process_a_pid": json.loads(EVIDENCE_A.read_text(encoding="utf-8"))["pid"]
        if EVIDENCE_A.exists()
        else None,
    }
    EVIDENCE_B.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    ok = (
        body["requirement"].startswith("Material factual claims")
        and body["workspace_id"] == TENANT
        and LESSON_NAME in hit_names
        and not leaked
        and evidence["contract_changed"]
        and evidence["process_a_pid"] != evidence["pid"]
    )
    print(json.dumps({"ok": ok, "evidence": "evidence/sibyl-kill-test-b.json", **evidence}, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
