import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]


def _safe_workspace_id(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.removeprefix("ws_")
    if len(raw) <= 8:
        return f"ws: {raw}"
    return f"ws: {raw[:4]}…{raw[-4:]}"


def _public_lesson(value: dict | None) -> dict | None:
    if not value:
        return None
    return {key: item for key, item in value.items() if key != "workspace_id"}


def _source_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def _source_tree_dirty() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(result.stdout.strip())

def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "https://prior.103-195-188-198.sslip.io"
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "evidence" / "stable-deployment-flow.json"
    if not base_url.lower().startswith("https://"):
        print("Stable deployment verification requires an HTTPS URL.")
        return 2
    print(f"Testing public deployment at: {base_url}")

    try:
        with httpx.Client(base_url=base_url, timeout=30.0, follow_redirects=True) as client:
            health_resp = client.get("/api/health")
            health_resp.raise_for_status()
            health = health_resp.json()
            print(f"Health: {health.get('overall')}")

            base_resp = client.get("/api/base/verify?network=mainnet")
            base_resp.raise_for_status()
            base_proof = base_resp.json()
            print(f"Base B20 read ok: {base_proof.get('ok')}, policyExists_0: {base_proof.get('policyExists_0')}")

            j1_resp = client.post("/api/jobs", json={"text": "Research the top five AI wallet companies."})
            j1_resp.raise_for_status()
            j1 = j1_resp.json()
            workspace_cookie = client.cookies.get("prior_workspace")
            print(f"Job 1 created: {j1['id']} in {_safe_workspace_id(workspace_cookie)}, baseline: {j1['contract']['baseline']}")

            hire_resp = client.post(f"/api/jobs/{j1['id']}/hire")
            hire_resp.raise_for_status()
            hire_data = hire_resp.json()
            findings = (hire_data.get("deliverable", {}).get("value", {}).get("findings", []))
            print(f"Job 1 hired: provider={hire_data.get('provider', {}).get('name')}, findings count={len(findings)}")

            rejection_reason = "Material factual claims must include identifiable source links."
            rej_resp = client.post(f"/api/jobs/{j1['id']}/reject", json={"reason": rejection_reason})
            rej_resp.raise_for_status()
            rej_data = rej_resp.json()
            proposed = rej_data.get("proposed_lesson", {})
            print(f"Job 1 rejected: proposed lesson={proposed.get('requirement')}")

            lesson_resp = client.post(f"/api/jobs/{j1['id']}/lessons", json={"action": "add"})
            lesson_resp.raise_for_status()
            lesson_data = lesson_resp.json()
            approved_lesson = lesson_data.get("proposed_lesson", {})
            print(f"Lesson approved: status={approved_lesson.get('status')}, id={approved_lesson.get('id')}")

            mem_resp = client.get("/api/memory")
            mem_resp.raise_for_status()
            mem_data = mem_resp.json()
            print(f"Memory count: {mem_data.get('count')}")

            j2_resp = client.post("/api/jobs", json={"text": "Research the top five decentralized exchanges."})
            j2_resp.raise_for_status()
            j2 = j2_resp.json()
            j2_contract = j2.get("contract", {})
            print(f"Job 2 created: baseline={j2_contract.get('baseline')}, applied_lessons count={len(j2_contract.get('applied_lessons', []))}")

            hire2_resp = client.post(f"/api/jobs/{j2['id']}/hire")
            hire2_resp.raise_for_status()
            hire2_data = hire2_resp.json()
            learned_in_worker = hire2_data.get("worker_requirement", {}).get("learned_requirements", [])
            print(f"Job 2 worker learned requirements: {learned_in_worker}")

            public_applied = [
                _public_lesson(item) for item in (j2_contract.get("applied_lessons") or [])
            ]
            evidence = {
                "pass": bool(
                    health.get("overall") in ["READY", "READY WITH WARNINGS"]
                    and health.get("build_commit") == _source_commit()
                    and base_proof.get("ok")
                    and j1.get("contract", {}).get("baseline") is True
                    and hire_data.get("provider", {}).get("source") == "local-development"
                    and len(findings) > 0
                    and approved_lesson.get("status") == "active"
                    and not j2_contract.get("baseline")
                    and len(j2_contract.get("applied_lessons", [])) > 0
                    and len(learned_in_worker) > 0
                ),
                "deployment_url": base_url,
                "deployment": {
                    "https": True,
                    "process_supervision": "systemd on VPS",
                    "persistent_storage": "Sibyl SQLite and job records under /var/lib/prior",
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "commit_hash": _source_commit(),
                "deployed_commit": health.get("build_commit"),
                "source_tree_dirty": _source_tree_dirty(),
                "workspace_id": _safe_workspace_id(workspace_cookie),
                "workspace_id_length": len(workspace_cookie or ""),
                "base_proof": {
                    "ok": base_proof.get("ok"),
                    "network": base_proof.get("network_name"),
                    "policy_registry": base_proof.get("policy_registry"),
                    "policyExists_0": base_proof.get("policyExists_0"),
                    "isB20_factory": base_proof.get("isB20_factory"),
                    "rpc": base_proof.get("rpc"),
                    "qualifies_as": base_proof.get("qualifies_as"),
                },
                "job_1": {
                    "id": j1["id"],
                    "baseline": j1["contract"]["baseline"],
                    "provider": hire_data.get("provider"),
                    "rejection_reason": rejection_reason,
                    "approved_lesson": _public_lesson(approved_lesson),
                },
                "job_2": {
                    "id": j2["id"],
                    "baseline": j2_contract.get("baseline"),
                    "applied_lessons": public_applied,
                    "worker_learned_requirements": learned_in_worker,
                },
                "sibyl_memory": {
                    "status": mem_data.get("status"),
                    "count": mem_data.get("count"),
                },
            }
    except Exception as exc:  # noqa: BLE001
        print(f"Deployment verification failed: {exc}")
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"Saved deployment evidence to {out_path}")
    return 0 if evidence["pass"] else 1

if __name__ == "__main__":
    sys.exit(main())
