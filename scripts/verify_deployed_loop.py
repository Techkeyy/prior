import json
import sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence" / "deployed-sibyl-flow.json"

def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "https://transcription-modern-tobago-dodge.trycloudflare.com"
    print(f"Testing public deployment at: {base_url}")
    
    with httpx.Client(base_url=base_url, timeout=30.0, follow_redirects=True) as client:
        # Step 0: Health & Base Verification
        health_resp = client.get("/api/health")
        health = health_resp.json()
        print(f"Health: {health.get('overall')}")
        
        base_resp = client.get("/api/base/verify?network=mainnet")
        base_proof = base_resp.json()
        print(f"Base B20 read ok: {base_proof.get('ok')}, policyExists_0: {base_proof.get('policyExists_0')}")
        
        # Step 1: Specify Job 1 (AI Wallets)
        j1_resp = client.post("/api/jobs", json={"text": "Research the top five AI wallet companies."})
        j1 = j1_resp.json()
        workspace_cookie = client.cookies.get("prior_workspace")
        print(f"Job 1 created: {j1['id']} in workspace: {workspace_cookie}, baseline: {j1['contract']['baseline']}")
        
        # Step 2: Hire Job 1
        hire_resp = client.post(f"/api/jobs/{j1['id']}/hire")
        hire_data = hire_resp.json()
        findings = (hire_data.get("deliverable", {}).get("value", {}).get("findings", []))
        print(f"Job 1 hired: provider={hire_data.get('provider', {}).get('name')}, findings count={len(findings)}")
        
        # Step 3: Reject Job 1
        rejection_reason = "Material factual claims must include identifiable source links."
        rej_resp = client.post(f"/api/jobs/{j1['id']}/reject", json={"reason": rejection_reason})
        rej_data = rej_resp.json()
        proposed = rej_data.get("proposed_lesson", {})
        print(f"Job 1 rejected: proposed lesson={proposed.get('requirement')}")
        
        # Step 4: Approve Lesson
        lesson_resp = client.post(f"/api/jobs/{j1['id']}/lessons", json={"action": "add"})
        lesson_data = lesson_resp.json()
        approved_lesson = lesson_data.get("proposed_lesson", {})
        print(f"Lesson approved: status={approved_lesson.get('status')}, id={approved_lesson.get('id')}")
        
        # Step 5: Verify Sibyl Memory View
        mem_resp = client.get("/api/memory")
        mem_data = mem_resp.json()
        print(f"Memory count: {mem_data.get('count')}")
        
        # Step 6: Job 2 in Same Workspace (DEX research)
        j2_resp = client.post("/api/jobs", json={"text": "Research the top five decentralized exchanges."})
        j2 = j2_resp.json()
        j2_contract = j2.get("contract", {})
        print(f"Job 2 created: baseline={j2_contract.get('baseline')}, applied_lessons count={len(j2_contract.get('applied_lessons', []))}")
        
        # Step 7: Hire Job 2
        hire2_resp = client.post(f"/api/jobs/{j2['id']}/hire")
        hire2_data = hire2_resp.json()
        learned_in_worker = hire2_data.get("worker_requirement", {}).get("learned_requirements", [])
        print(f"Job 2 worker learned requirements: {learned_in_worker}")
        
        evidence = {
            "pass": bool(
                health.get("overall") in ["READY", "READY WITH WARNINGS"]
                and base_proof.get("ok")
                and not j2_contract.get("baseline")
                and len(j2_contract.get("applied_lessons", [])) > 0
                and len(learned_in_worker) > 0
            ),
            "deployment_url": base_url,
            "workspace_id": workspace_cookie,
            "base_proof": {
                "ok": base_proof.get("ok"),
                "network": base_proof.get("network_name"),
                "policy_registry": base_proof.get("policy_registry"),
                "policyExists_0": base_proof.get("policyExists_0"),
                "isB20_factory": base_proof.get("isB20_factory"),
                "rpc": base_proof.get("rpc"),
                "qualifies_as": base_proof.get("qualifies_as")
            },
            "job_1": {
                "id": j1["id"],
                "baseline": j1["contract"]["baseline"],
                "provider": hire_data.get("provider"),
                "rejection_reason": rejection_reason,
                "approved_lesson": approved_lesson
            },
            "job_2": {
                "id": j2["id"],
                "baseline": j2_contract.get("baseline"),
                "applied_lessons": j2_contract.get("applied_lessons"),
                "worker_learned_requirements": learned_in_worker
            },
            "sibyl_memory": {
                "status": mem_data.get("status"),
                "count": mem_data.get("count")
            }
        }
        
        OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(f"Saved deployment evidence to {OUT}")
        return 0 if evidence["pass"] else 1

if __name__ == "__main__":
    sys.exit(main())
