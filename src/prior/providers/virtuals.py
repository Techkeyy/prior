"""Virtuals ACP v2 provider. Fails honestly if credentials are missing.

Uses @virtuals-protocol/acp-node-v2 via acp-bridge with
PrivyAlchemyEvmProviderAdapter. Never falls back to LOCAL PROVIDER.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from prior.domain import AgentOffer, Contract, JobSpec
from prior.providers.base import (
    VIRTUALS_NOT_CONFIGURED,
    ProviderError,
    ProviderJob,
    requirement_payload,
)
from prior.settings import ROOT, acp_env, acp_ready, missing_virtuals_credentials

BRIDGE = ROOT / "acp-bridge" / "run.mjs"
VIRTUALS_SOURCE = "virtuals-acp"


class VirtualsAcpProvider:
    kind = "virtuals-acp"

    def find_providers(self, spec: JobSpec) -> list[AgentOffer]:
        self._require_ready()
        raw = _bridge(["browse", spec.domain or spec.subject or "research"])
        offers: list[AgentOffer] = []
        for item in raw.get("agents") or []:
            offers.append(
                AgentOffer(
                    id=str(item.get("walletAddress") or item.get("id") or ""),
                    name=str(item.get("name") or "Unnamed ACP agent"),
                    summary=str(item.get("description") or item.get("offeringName") or ""),
                    price_label=str(item.get("price") if item.get("price") is not None else ""),
                    source=VIRTUALS_SOURCE,
                    network="Virtuals ACP",
                    wallet_address=item.get("walletAddress"),
                    offering_name=item.get("offeringName"),
                )
            )
        if not offers:
            raise ProviderError(
                "Virtuals ACP browse returned no research providers. "
                "Register a PRIOR research seller, then retry."
            )
        return offers

    def create_job(self, offer: AgentOffer, contract: Contract, spec: JobSpec) -> ProviderJob:
        self._require_ready()
        if offer.source != VIRTUALS_SOURCE:
            raise ProviderError("VirtualsAcpProvider will not create a non-ACP job.")
        if not offer.wallet_address or not offer.offering_name:
            raise ProviderError("ACP offering is missing wallet address or offering name.")
        requirement = requirement_payload(contract, spec)
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
            raise ProviderError(f"ACP create-job returned no jobId: {raw}")
        return ProviderJob(
            source=VIRTUALS_SOURCE,
            phase=str(raw.get("phase") or "job.created"),
            offer=offer,
            requirement=requirement,
            acp_job_id=str(job_id),
        )

    def get_job_status(self, job: ProviderJob) -> ProviderJob:
        self._require_ready()
        if not job.acp_job_id:
            raise ProviderError("Cannot read ACP status: missing job id.")
        raw = _bridge(["status", job.acp_job_id])
        job.phase = str(raw.get("phase") or job.phase)
        if raw.get("deliverable"):
            job.deliverable = raw["deliverable"]
        if raw.get("txHash"):
            job.extra["txHash"] = raw["txHash"]
        return job

    def get_deliverable(self, job: ProviderJob) -> dict[str, Any] | None:
        if job.deliverable:
            return job.deliverable
        updated = self.get_job_status(job)
        return updated.deliverable

    def evaluate(self, job: ProviderJob, accepted: bool, reason: str) -> ProviderJob:
        self._require_ready()
        if not job.acp_job_id:
            raise ProviderError("Cannot evaluate: missing ACP job id.")
        action = "complete" if accepted else "reject"
        raw = _bridge([action, str(job.acp_job_id), reason])
        job.phase = "job.completed" if accepted else "job.rejected"
        job.extra["evaluate_response"] = {k: v for k, v in raw.items() if k != "error"}
        return job

    def _require_ready(self) -> None:
        if not acp_ready():
            missing = missing_virtuals_credentials()
            detail = VIRTUALS_NOT_CONFIGURED
            if missing:
                detail = f"{VIRTUALS_NOT_CONFIGURED} Missing: {', '.join(missing)}."
            raise ProviderError(detail)


def _bridge(args: list[str]) -> dict[str, Any]:
    if not BRIDGE.exists():
        raise ProviderError(
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
        raise ProviderError("Node.js is required for the official Virtuals ACP SDK v2.")
    proc = subprocess.run(
        [node, str(BRIDGE), *args],
        cwd=str(BRIDGE.parent),
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "ACP bridge failed").strip()
        raise ProviderError(detail)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"ACP bridge returned non-JSON: {proc.stdout[:500]}") from exc
