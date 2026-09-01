"""Virtuals ACP adapter.

Uses the official Node SDK (@virtuals-protocol/acp-node-v2) via acp-bridge.
Python virtuals-acp cannot install on Python 3.14 (requires <3.13).

This module never invents job ids, prices, or transaction hashes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from prior.domain import AgentOffer, Contract
from prior.settings import ROOT, acp_env, acp_ready, local_provider_enabled

BRIDGE = ROOT / "acp-bridge" / "run.mjs"


class AcpUnavailable(RuntimeError):
    pass


def discover_or_fail() -> list[AgentOffer]:
    if acp_ready():
        raw = _bridge(["browse", "research"])
        offers = []
        for item in raw.get("agents") or []:
            offers.append(
                AgentOffer(
                    id=str(item.get("walletAddress") or item.get("id") or ""),
                    name=str(item.get("name") or "Unnamed ACP agent"),
                    summary=str(item.get("description") or item.get("offeringName") or ""),
                    price_label=str(item.get("price") or item.get("priceUsd") or ""),
                    source="virtuals-acp",
                    wallet_address=item.get("walletAddress"),
                    offering_name=item.get("offeringName"),
                )
            )
        if not offers:
            raise AcpUnavailable(
                "Virtuals ACP browse returned no research providers. "
                "Register a PRIOR research seller, then retry."
            )
        return offers
    if local_provider_enabled():
        return [
            AgentOffer(
                id="local-research-provider",
                name="PRIOR local research provider",
                summary="Runs on this machine. Not a Virtuals ACP job.",
                price_label="no onchain payment",
                source="local-development",
            )
        ]
    raise AcpUnavailable(
        "Virtuals ACP is not configured. Set ACP_ENABLED=true and the buyer wallet "
        "credentials from the Virtuals registry. This build will not invent a worker."
    )


def initiate_job(offer: AgentOffer, contract: Contract, spec: dict[str, Any]) -> dict[str, Any]:
    requirement = {
        "goal": contract.goal,
        "title": contract.title,
        "deliverables": contract.deliverables,
        "acceptance": contract.acceptance,
        "applied_lessons": [lesson.to_dict() for lesson in contract.applied_lessons],
        "raw": spec.get("raw"),
        "subject": spec.get("subject"),
        "domain": spec.get("domain"),
        "time_sensitive": spec.get("time_sensitive"),
    }
    if offer.source == "virtuals-acp":
        if not offer.wallet_address or not offer.offering_name:
            raise AcpUnavailable("ACP offering is missing wallet address or offering name.")
        raw = _bridge(
            [
                "create-job",
                offer.wallet_address,
                offer.offering_name,
                json.dumps(requirement),
            ]
        )
        job_id = raw.get("jobId")
        if not job_id:
            raise AcpUnavailable(f"ACP create-job returned no jobId: {raw}")
        return {
            "source": "virtuals-acp",
            "acp_job_id": str(job_id),
            "phase": raw.get("phase") or "job.created",
            "provider": offer.to_dict(),
            "requirement": requirement,
        }
    if offer.source == "local-development" and local_provider_enabled():
        return {
            "source": "local-development",
            "acp_job_id": None,
            "phase": "local.working",
            "provider": offer.to_dict(),
            "requirement": requirement,
        }
    raise AcpUnavailable("No honest hire path is available.")


def evaluate_job(acp_job_id: str | None, source: str, accepted: bool, reason: str) -> dict[str, Any]:
    if source == "virtuals-acp":
        if not acp_job_id:
            raise AcpUnavailable("Cannot evaluate: missing ACP job id.")
        action = "complete" if accepted else "reject"
        return _bridge([action, str(acp_job_id), reason])
    return {"source": source, "evaluated": accepted, "reason": reason, "onchain": False}


def _bridge(args: list[str]) -> dict[str, Any]:
    if not BRIDGE.exists():
        raise AcpUnavailable(
            f"ACP bridge missing at {BRIDGE}. Official Virtuals jobs cannot start."
        )
    env = os.environ.copy()
    for key, value in acp_env().items():
        if value:
            env[key] = value
    node_dir = Path(r"C:\Program Files\nodejs")
    if node_dir.exists():
        env["PATH"] = str(node_dir) + os.pathsep + env.get("PATH", "")
    node = shutil.which("node", path=env.get("PATH"))
    if not node:
        raise AcpUnavailable("Node.js is required for the official Virtuals ACP SDK v2.")
    proc = subprocess.run(
        [node, str(BRIDGE), *args],
        cwd=str(BRIDGE.parent),
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "ACP bridge failed").strip()
        raise AcpUnavailable(detail)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AcpUnavailable(f"ACP bridge returned non-JSON: {proc.stdout[:500]}") from exc
