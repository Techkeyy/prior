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

def main():
    print("=== EXECUTING REAL PRODUCTION ACP UAT JOB ===")
    client = ProductionClient()

    # 1. Check workspace
    status, ws = client.request("GET", "/api/workspace")
    print(f"1. Workspace: {ws['workspace_id']} | Hire mode: {ws['hire_mode']}")

    # 2. Specify job with exact UAT prompt
    spec_text = "Research the top five AI wallet companies and compare their products, pricing, strengths, and weaknesses."
    print(f"2. Specifying job: '{spec_text}'")
    status, job = client.request("POST", "/api/jobs", {"text": spec_text})
    job_id = job["id"]
    print(f"   Created Job ID: {job_id} | Status: {job['status']}")

    # 3. Hire agent via Virtuals ACP on Base mainnet
    print("3. Hiring agent via Virtuals ACP on Base mainnet...")
    hire_start = time.time()
    status, hired = client.request("POST", f"/api/jobs/{job_id}/hire")
    acp_job_id = hired.get("acp_job_id")
    provider_name = hired.get("provider_name")
    print(f"   Hired! On-chain ACP Job ID: {acp_job_id} | Provider: {provider_name}")

    # 4. Poll until deliverable is returned by VPS seller service
    print("4. Polling until deliverable is returned by VPS seller...")
    poll_start = time.time()
    deliverable = None
    for i in range(60):
        time.sleep(4)
        status, updated = client.request("GET", f"/api/jobs/{job_id}")
        current_status = updated.get("status")
        phase = updated.get("provider_metadata", {}).get("phase")
        print(f"   [{i*4}s] Status: {current_status} | Phase: {phase}")
        if updated.get("deliverable"):
            deliverable = updated.get("deliverable")
            break

    assert deliverable is not None, "Failed to receive deliverable"
    elapsed = time.time() - poll_start
    print(f"\nDeliverable received in {elapsed:.1f}s!")

    val = deliverable.get("value", deliverable) if isinstance(deliverable, dict) else deliverable
    print("\n--- DELIVERABLE VALUE ---")
    print(json.dumps(val, indent=2))

    findings = val.get("findings", [])
    print(f"\nTotal findings returned: {len(findings)}")
    for f in findings:
        print(f"- Name: {f.get('name')}")
        print(f"  Summary: {str(f.get('summary'))[:120]}...")
        print(f"  Pricing: {f.get('pricing')}")
        print(f"  Strengths: {str(f.get('strengths'))[:100]}...")
        print(f"  Weaknesses: {str(f.get('weaknesses'))[:100]}...")
        print(f"  Sources: {f.get('sources')}")

    with open("evidence/production-uat-fix-job.json", "w") as f:
        json.dump({
            "job_id": job_id,
            "acp_job_id": acp_job_id,
            "prompt": spec_text,
            "deliverable": val,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }, f, indent=2)

if __name__ == "__main__":
    main()
