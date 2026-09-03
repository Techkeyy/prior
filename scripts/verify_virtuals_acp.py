"""Virtuals ACP v2 Gold-Standard Learning Verification.

Validates credentials, creates real ACP jobs, sends PRIOR dynamic requirements,
executes Sibyl learning loop across 2 jobs, and records sanitized evidence.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prior import service, settings
from prior.memory import list_lessons
from prior.providers.virtuals import VirtualsAcpProvider
from prior.settings import missing_virtuals_credentials

OUT = ROOT / "evidence" / "virtuals-acp-live.json"
PACKAGE = "@virtuals-protocol/acp-node-v2"
PACKAGE_VERSION = "0.1.12"


def _write_evidence(payload: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _node() -> str:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required for the official Virtuals ACP SDK v2.")
    return node


def _bridge(*args: str) -> dict:
    proc = subprocess.run(
        [_node(), "run.mjs", *args],
        cwd=str(ROOT / "acp-bridge"),
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "ACP bridge failed").strip())
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ACP bridge returned non-JSON: {proc.stdout[:500]}") from exc


def _start_seller() -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [_node(), "seller.mjs"],
        cwd=str(ROOT / "acp-bridge"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
    )
    time.sleep(5)
    if process.poll() is not None:
        detail = (process.stderr.read() if process.stderr else "").strip()
        raise RuntimeError(f"Seller listener exited before readiness: {detail}")
    return process


def _fund_until_ready(job_id: str, timeout: int = 90) -> dict:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            return _bridge("fund", job_id)
        except Exception as exc:  # seller may not have set its budget yet
            last_error = str(exc)
            time.sleep(3)
    raise RuntimeError(f"ACP funding did not become available: {last_error}")


def _wait_for_deliverable(job_id: str, timeout: int = 180) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = _bridge("status", job_id)
        if status.get("deliverable"):
            return status
        if status.get("phase") in {"completed", "rejected", "expired"}:
            raise RuntimeError(f"ACP job reached {status.get('phase')} without a deliverable.")
        time.sleep(4)
    raise RuntimeError("Timed out waiting for ACP seller deliverable.")


def _acp_enabled() -> bool:
    return os.getenv("ACP_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    print("=== Virtuals ACP v2 Verification ===")
    missing_buyer = missing_virtuals_credentials(role="buyer")
    missing_seller = missing_virtuals_credentials(role="seller")
    credentials_present = not missing_buyer and not missing_seller

    if missing_buyer or missing_seller or not _acp_enabled():
        missing_configuration = [] if _acp_enabled() else ["ACP_ENABLED=true"]
        evidence = {
            "pass": False,
            "status": "NOT VERIFIED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "package": PACKAGE,
            "package_version": PACKAGE_VERSION,
            "credentials_present": credentials_present,
            "missing_credentials": {"buyer": missing_buyer, "seller": missing_seller},
            "missing_configuration": missing_configuration,
            "registered_buyer": None,
            "registered_seller": None,
            "seller_offering": None,
            "real_acp_job": False,
            "evidence_note": (
                "Credentials are absent. No ACP request was attempted."
                if not credentials_present
                else "ACP_ENABLED is not true. No ACP request was attempted."
            ),
        }
        _write_evidence(evidence)
        if credentials_present:
            print("[STATUS] ACP_ENABLED is not true.")
        else:
            print("[STATUS] Virtuals ACP credentials not present.")
        print(f"  Missing buyer credentials: {missing_buyer}")
        print(f"  Missing seller credentials: {missing_seller}")
        print("  PRIOR will fail honestly rather than fake an ACP job.")
        return 1

    print("[STATUS] Virtuals credentials present. Executing real buyer/seller ACP test...")
    seller = None
    try:
        seller = _start_seller()
        provider = VirtualsAcpProvider()
        ws = "ws_virtuals_acp_" + uuid.uuid4().hex[:12]

        spec1 = service.specify(ws, "Research the top five AI wallet companies.")
        offers = provider.find_providers(spec1.spec)
        seller_address = os.environ["SELLER_WALLET_ADDRESS"].lower()
        seller_offers = [
            offer for offer in offers
            if (offer.wallet_address or "").lower() == seller_address and offer.offering_name
        ]
        if not seller_offers:
            raise RuntimeError("Registered seller was found without a research offering.")
        print(f"Confirmed seller offering: {seller_offers[0].offering_name}")

        hired1 = service.hire(ws, spec1.id)
        if not hired1.acp_job_id:
            raise RuntimeError("ACP create-job returned no real job id.")
        _fund_until_ready(hired1.acp_job_id)
        _wait_for_deliverable(hired1.acp_job_id)
        delivered1 = service.refresh(ws, spec1.id)
        if delivered1.status != "delivered":
            raise RuntimeError(f"PRIOR did not record ACP Job 1 as delivered: {delivered1.status}")
        service.reject(ws, spec1.id, "Material factual claims must include identifiable source links.")
        lesson = service.decide_lesson(ws, spec1.id, "add")
        print(f"Lesson written to Sibyl: {lesson.proposed_lesson['requirement']}")

        spec2 = service.specify(ws, "Research the top five decentralized exchanges.")
        if spec2.contract.baseline or not spec2.contract.applied_lessons:
            raise RuntimeError("Job 2 did not recall and apply the Sibyl lesson.")
        hired2 = service.hire(ws, spec2.id)
        learned_requirements = hired2.worker_requirement.get("learned_requirements", [])
        _fund_until_ready(hired2.acp_job_id)
        _wait_for_deliverable(hired2.acp_job_id)
        delivered2 = service.refresh(ws, spec2.id)
        if delivered2.status != "delivered":
            raise RuntimeError(f"PRIOR did not record ACP Job 2 as delivered: {delivered2.status}")
        completed2 = service.accept(ws, spec2.id)
        evidence = {
            "pass": bool(completed2.status == "accepted" and completed2.acp_phase in {"completed", "job.completed"}),
            "status": "VERIFIED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "virtuals-acp",
            "package": PACKAGE,
            "package_version": PACKAGE_VERSION,
            "credentials_present": True,
            "registered_buyer": True,
            "registered_seller": True,
            "seller_offering": seller_offers[0].offering_name,
            "real_acp_job": True,
            "job_1": {
                "id": spec1.id,
                "acp_job_id": hired1.acp_job_id,
                "provider": hired1.provider,
                "baseline": True,
                "terminal_action": "rejected after a real deliverable",
            },
            "job_2": {
                "id": spec2.id,
                "acp_job_id": hired2.acp_job_id,
                "phase": completed2.acp_phase,
                "baseline": False,
                "learned_requirements": learned_requirements,
                "terminal_action": "accepted",
            },
            "sibyl_memory": {
                "status": "ok",
                "lessons_count": len(list_lessons(ws)),
            },
        }
        _write_evidence(evidence)
        print(f"Saved Virtuals ACP evidence to {OUT}")
        return 0 if evidence["pass"] else 1
    except Exception as exc:  # noqa: BLE001
        evidence = {
            "pass": False,
            "status": "NOT VERIFIED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "package": PACKAGE,
            "package_version": PACKAGE_VERSION,
            "credentials_present": True,
            "registered_buyer": None,
            "registered_seller": None,
            "seller_offering": None,
            "real_acp_job": False,
            "error": str(exc),
        }
        _write_evidence(evidence)
        print(f"[STATUS] Virtuals ACP verification failed honestly: {exc}")
        return 1
    finally:
        if seller and seller.poll() is None:
            seller.terminate()
            try:
                seller.wait(timeout=10)
            except subprocess.TimeoutExpired:
                seller.kill()


if __name__ == "__main__":
    sys.exit(main())
