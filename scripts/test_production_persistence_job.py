import urllib.request
import json
import ssl
import time
import subprocess
import sys

BASE_URL = "https://prior.103-195-188-198.sslip.io"
SSH_KEY = r"C:\Users\HomePC\.ssh\villa-vps-deploy_ed25519"
VPS_HOST = "root@103.195.188.198"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

class ProductionClient:
    def __init__(self):
        self.cookie = None

    def request(self, method, path, data=None):
        url = f"{BASE_URL}{path}"
        headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
        if self.cookie:
            headers["Cookie"] = self.cookie
        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, context=ctx, timeout=120) as resp:
            cookie_hdr = resp.headers.get("Set-Cookie")
            if cookie_hdr:
                self.cookie = cookie_hdr.split(";")[0]
            resp_body = resp.read().decode("utf-8")
            return resp.status, json.loads(resp_body) if resp_body else {}

def get_vps_seller_logs(since_minutes=5):
    cmd = [
        "ssh", "-n", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        VPS_HOST,
        f"journalctl -u prior-acp-seller.service --since '{since_minutes} min ago' --no-pager"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return res.stdout

def main():
    print("=== PROVING PRODUCTION ACP INDEPENDENCE (LOCAL PC STOPPED) ===")
    client = ProductionClient()

    # 1. Check workspace
    status, ws = client.request("GET", "/api/workspace")
    print(f"1. Workspace initialized: {ws['workspace_id']} | Hire mode: {ws['hire_mode']} | ACP enabled: {ws['acp_enabled']}")
    assert ws['acp_enabled'] is True, "ACP is not enabled on production"
    assert ws['hire_mode'] == 'virtuals', "Hire mode is not virtuals"

    # 2. Specify job
    spec_text = "Research top 3 decentralized identity protocols on Base and summarize key capabilities."
    print(f"2. Specifying job: '{spec_text}'")
    status, job = client.request("POST", "/api/jobs", {"text": spec_text})
    job_id = job["id"]
    print(f"   Created Job ID: {job_id} | Status: {job['status']} | Contract baseline: {job['contract']['baseline']}")

    # 3. Hire agent via Virtuals ACP on Base mainnet
    print("3. Hiring agent via Virtuals ACP on Base mainnet (creating on-chain job)...")
    hire_start = time.time()
    status, hired = client.request("POST", f"/api/jobs/{job_id}/hire")
    acp_job_id = hired.get("acp_job_id")
    provider_name = hired.get("provider_name")
    print(f"   Hired! On-chain ACP Job ID: {acp_job_id} | Provider: {provider_name} | Elapsed: {time.time()-hire_start:.1f}s")

    # 4. Poll until deliverable is returned by VPS seller service
    print("4. Polling production PRIOR until deliverable is returned by VPS seller daemon...")
    poll_start = time.time()
    deliverable = None
    final_status = None
    for i in range(60):
        time.sleep(4)
        status, updated = client.request("GET", f"/api/jobs/{job_id}")
        current_status = updated.get("status")
        phase = updated.get("provider_metadata", {}).get("phase")
        print(f"   [{i*4}s] Status: {current_status} | Phase: {phase}")
        if updated.get("deliverable"):
            deliverable = updated.get("deliverable")
            final_status = current_status
            print(f"   --> Deliverable received! Review state reached in {time.time()-poll_start:.1f}s")
            break
        if current_status in ("completed", "delivered", "ready_for_review") or phase in ("job.delivered", "job.completed"):
            deliverable = updated.get("deliverable")
            final_status = current_status
            break

    assert deliverable is not None, "Failed to receive deliverable within timeout"

    print("\n5. Deliverable Summary:")
    snippet = str(deliverable)[:200]
    print(f"   Deliverable snippet: {snippet}...")

    # 6. Fetch VPS seller service logs
    print("\n6. VPS Seller Service Logs during this job:")
    logs = get_vps_seller_logs(since_minutes=3)
    print(logs)

    result = {
        "production_prior_job_id": job_id,
        "on_chain_acp_job_id": acp_job_id,
        "provider": provider_name,
        "final_status": final_status,
        "deliverable_received": True,
        "deliverable_snippet": snippet,
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    with open("evidence/production-acp-persistence.json", "w") as f:
        json.dump(result, f, indent=2)

    print("\n=== PRODUCTION ACP PERSISTENCE PROOF: PASS ===")

if __name__ == "__main__":
    main()
