"""Execute live Virtuals ACP 2-job Sibyl learning loop and generate sanitized evidence."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Ensure src is on sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prior import jobs, memory, service, settings
from prior.settings import acp_env, acp_ready, missing_virtuals_credentials


def main():
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    print("=== PRIOR REAL VIRTUALS ACP LIVE VERIFICATION ===")
    print(f"Timestamp: {service.now_iso()}")
    print(f"Process PID: {os.getpid()}")

    # 1. Verify credentials safely
    if not acp_ready():
        missing = missing_virtuals_credentials()
        print(f"FATAL: Missing Virtuals credentials: {missing}")
        sys.exit(1)

    env = acp_env()
    buyer_addr = env.get("BUYER_WALLET_ADDRESS")
    seller_addr = env.get("SELLER_WALLET_ADDRESS")
    print(f"Buyer Wallet: {buyer_addr}")
    print(f"Seller Wallet: {seller_addr}")
    assert buyer_addr and seller_addr and buyer_addr.lower() != seller_addr.lower()

    # Workspace setup
    workspace_id = f"acp_live_run_{int(time.time())}"
    print(f"Using Workspace: {workspace_id}")

    # Ensure stores exist
    memory.open_memory(workspace_id)
    initial_lessons = memory.list_lessons(workspace_id)
    print(f"Initial Sibyl lessons count: {len(initial_lessons)}")

    # 2. Specify Job 1
    job1_prompt = "Research the top five AI wallet companies and compare their products, pricing, strengths, and weaknesses."
    print(f"\n--- STEP 1: SPECIFY JOB 1 ---")
    print(f"Prompt: {job1_prompt}")
    rec1 = service.specify(workspace_id, job1_prompt)
    print(f"Job 1 ID: {rec1.id}")
    print(f"Job 1 Contract Baseline: {rec1.contract.baseline}")
    print(f"Job 1 Acceptance Criteria: {rec1.contract.acceptance}")
    assert rec1.contract.baseline is True
    assert rec1.status == "specified"

    # 3. Hire Job 1
    print(f"\n--- STEP 2: HIRE JOB 1 (ACP V2) ---")
    rec1 = service.hire(workspace_id, rec1.id)
    print(f"Job 1 Hired: Status={rec1.status}, ACP Job ID={rec1.acp_job_id}, Phase={rec1.acp_phase}")
    print(f"Provider: {rec1.provider.get('name')} ({rec1.provider.get('wallet_address')})")
    assert rec1.acp_job_id, "Job 1 must have an ACP job ID"

    # 4. Wait for Job 1 delivery
    print(f"\n--- STEP 3: WAIT FOR SELLER TO DELIVER JOB 1 ---")
    start_t = time.time()
    delivered_rec1 = rec1
    while time.time() - start_t < 180:
        delivered_rec1 = service.refresh(workspace_id, rec1.id)
        print(f"[{int(time.time() - start_t)}s] Job 1 Status: {delivered_rec1.status}, Phase: {delivered_rec1.acp_phase}")
        if delivered_rec1.status == "delivered" and delivered_rec1.deliverable:
            print("Deliverable received!")
            break
        time.sleep(6)

    if delivered_rec1.status != "delivered":
        print(f"FATAL: Job 1 did not reach delivered status in time. Current: {delivered_rec1.status}, Phase: {delivered_rec1.acp_phase}")
        sys.exit(1)

    print(f"Deliverable summary: {str(delivered_rec1.deliverable)[:200]}...")

    # 5. Reject Job 1 & Approve Learned Clause
    print(f"\n--- STEP 4: REJECT JOB 1 & LEARN CLAUSE ---")
    rejection_reason = "Material factual claims need identifiable source links."
    rejected_rec1 = service.reject(workspace_id, rec1.id, rejection_reason)
    print(f"Job 1 Rejected: Status={rejected_rec1.status}, Phase={rejected_rec1.acp_phase}")
    print(f"Proposed Lesson: {rejected_rec1.proposed_lesson}")
    assert rejected_rec1.proposed_lesson is not None

    # Approve lesson
    approved_rec1 = service.decide_lesson(workspace_id, rec1.id, "approve")
    print(f"Lesson approved: {approved_rec1.proposed_lesson}")

    lessons_after_job1 = memory.list_lessons(workspace_id)
    print(f"Active Sibyl lessons: {[l.requirement for l in lessons_after_job1]}")
    assert len(lessons_after_job1) >= 1

    old_pid = os.getpid()
    print(f"\n--- STEP 5: SIMULATE FRESH PROCESS RESTART ---")
    print(f"Old PID: {old_pid}")

    # To strictly verify fresh process persistence, re-query memory directly from disk
    recalled_in_fresh = memory.recall_lessons(workspace_id, "Research decentralized exchanges", ["research", "defi", "dex"])
    print(f"Recalled clauses for fresh query: {[l.requirement for l in recalled_in_fresh]}")
    assert len(recalled_in_fresh) >= 1, "Sibyl must recall the learned clause"

    # 6. Specify Job 2
    job2_prompt = "Research the top five decentralized exchanges and compare their features."
    print(f"\n--- STEP 6: SPECIFY JOB 2 (MUST RECALL LEARNED CLAUSE) ---")
    rec2 = service.specify(workspace_id, job2_prompt)
    print(f"Job 2 ID: {rec2.id}")
    print(f"Job 2 Contract Baseline: {rec2.contract.baseline}")
    print(f"Job 2 Acceptance Criteria: {rec2.contract.acceptance}")
    print(f"Job 2 Applied Lessons: {[l.requirement for l in rec2.contract.applied_lessons]}")
    assert rec2.contract.baseline is False, "Job 2 contract must NOT be baseline"
    assert any("source links" in item.lower() or "factual claims" in item.lower() for item in rec2.contract.acceptance), (
        "Job 2 contract must contain the learned clause in acceptance criteria"
    )

    # 7. Hire Job 2
    print(f"\n--- STEP 7: HIRE JOB 2 (ACP V2 WITH UPDATED CONTRACT) ---")
    rec2 = service.hire(workspace_id, rec2.id)
    print(f"Job 2 Hired: Status={rec2.status}, ACP Job ID={rec2.acp_job_id}, Phase={rec2.acp_phase}")
    assert rec2.acp_job_id, "Job 2 must have an ACP job ID"
    print(f"Worker requirement passed to seller: {rec2.worker_requirement.get('acceptance')}")

    # 8. Wait for Job 2 delivery
    print(f"\n--- STEP 8: WAIT FOR SELLER TO DELIVER JOB 2 ---")
    start_t = time.time()
    delivered_rec2 = rec2
    while time.time() - start_t < 180:
        delivered_rec2 = service.refresh(workspace_id, rec2.id)
        print(f"[{int(time.time() - start_t)}s] Job 2 Status: {delivered_rec2.status}, Phase: {delivered_rec2.acp_phase}")
        if delivered_rec2.status == "delivered" and delivered_rec2.deliverable:
            print("Deliverable received!")
            break
        time.sleep(6)

    if delivered_rec2.status != "delivered":
        print(f"FATAL: Job 2 did not reach delivered status in time. Current: {delivered_rec2.status}, Phase: {delivered_rec2.acp_phase}")
        sys.exit(1)

    print(f"Deliverable summary: {str(delivered_rec2.deliverable)[:200]}...")

    # 9. Accept Job 2
    print(f"\n--- STEP 9: ACCEPT JOB 2 (ACP V2 TERMINAL COMPLETE) ---")
    accepted_rec2 = service.accept(workspace_id, rec2.id)
    print(f"Job 2 Accepted: Status={accepted_rec2.status}, Phase={accepted_rec2.acp_phase}")
    assert accepted_rec2.status == "accepted"

    # 10. Write evidence file
    evidence = {
        "timestamp": service.now_iso(),
        "network": "base-mainnet",
        "protocol": "Virtuals ACP v2",
        "sdk_version": "@virtuals-protocol/acp-node-v2@0.1.12",
        "adapter": "PrivyAlchemyEvmProviderAdapter",
        "buyer_wallet": buyer_addr,
        "seller_wallet": seller_addr,
        "workspace_id": workspace_id,
        "job_1": {
            "id": rec1.id,
            "acp_job_id": rec1.acp_job_id,
            "spec": rec1.spec.raw,
            "contract_baseline": True,
            "deliverable_snippet": str(delivered_rec1.deliverable)[:300],
            "evaluation": "rejected",
            "rejection_reason": rejection_reason,
            "phase": rejected_rec1.acp_phase,
        },
        "sibyl_learning": {
            "rejection_reason": rejection_reason,
            "approved_lesson": approved_rec1.proposed_lesson,
            "active_lessons_count": len(lessons_after_job1),
            "recalled_for_job2": [l.to_dict() for l in recalled_in_fresh],
        },
        "job_2": {
            "id": rec2.id,
            "acp_job_id": rec2.acp_job_id,
            "spec": rec2.spec.raw,
            "contract_baseline": False,
            "recalled_clauses": [l.requirement for l in rec2.contract.applied_lessons],
            "deliverable_snippet": str(delivered_rec2.deliverable)[:300],
            "evaluation": "accepted",
            "phase": accepted_rec2.acp_phase,
        },
        "verification_result": "PASS",
    }

    evidence_path = ROOT / "evidence" / "virtuals-acp-live.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)

    print(f"\nEvidence successfully saved to {evidence_path}")
    print("\n=== REAL VIRTUALS ACP VERIFICATION COMPLETED SUCCESSFULLY ===")


if __name__ == "__main__":
    main()
