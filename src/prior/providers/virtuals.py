"""Virtuals ACP v2 provider. Fails honestly if credentials are missing.

Uses @virtuals-protocol/acp-node-v2 via acp-bridge with
PrivyAlchemyEvmProviderAdapter. Never falls back to LOCAL PROVIDER.

Two execution paths exist. The historical path (find_providers +
create_job) hires through the previously configured seller. The dynamic
path (prepare_hire + execute_hire) hires the marketplace-selected offering
from a frozen HirePlan and performs no independent discovery.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from prior.domain import AgentOffer, Contract, JobRecord, JobSpec
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
                    offering_name=item.get("offeringName") or "research",
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
        if not offer.wallet_address:
            raise ProviderError("ACP offering is missing wallet address.")
        offering_name = offer.offering_name or "research"
        requirement = requirement_payload(contract, spec)
        raw = _bridge(
            [
                "create-job",
                offer.wallet_address,
                offering_name,
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
        if raw.get("expiredAt") not in (None, ""):
            job.extra["expiredAt"] = str(raw["expiredAt"])
        if isinstance(raw.get("budget"), dict):
            job.extra["budget"] = raw["budget"]
        if raw.get("sessionStatus") not in (None, ""):
            job.extra["sessionStatus"] = str(raw["sessionStatus"])
        if isinstance(raw.get("funded"), bool):
            job.extra["funded"] = raw["funded"]
        if isinstance(raw.get("history"), list):
            job.extra["history"] = raw["history"][:20]
        try:
            job.extra["chainId"] = int(raw.get("chainId"))
        except (TypeError, ValueError):
            job.extra["chainId"] = None
        if raw.get("deliverable"):
            job.deliverable = _decode_deliverable(raw["deliverable"])
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

    def prepare_hire(self, record: JobRecord, discover=None) -> dict[str, Any]:
        """Select a live marketplace offering and freeze a HirePlan.

        Read-only: runs discovery plus deterministic selection, never writes.
        Live discovery requires buyer credentials; an explicitly injected
        discover callable is a controlled/test path and skips that gate.
        """
        from prior import hiring as hiring_mod
        from prior.marketplace import select_provider_for_spec

        if discover is None:
            self._require_ready()
        selection = select_provider_for_spec(
            record.spec, record.contract, discover=discover)
        plan = hiring_mod.build_hire_plan(record, selection)
        return plan.to_dict()

    def refresh_selected_offering(self, plan_dict: dict[str, Any]) -> dict[str, Any]:
        """Read-only freshness lookup for the plan's exact provider+offering.

        Uses getAgentByWalletAddress (official SDK read). Never searches,
        never selects, never writes. Raises ProviderError when the provider
        or offering is gone or the lookup itself fails.
        """
        from prior import hiring as hiring_mod

        self._require_ready()
        plan = hiring_mod.HirePlan.from_dict(plan_dict or {})
        if not plan.provider_wallet or not plan.offering_name:
            raise ProviderError("HirePlan is missing provider or offering identity.")
        raw = _bridge(["offering-refresh", plan.provider_wallet, plan.offering_name])
        if not isinstance(raw, dict) or not raw.get("found") or not raw.get("offering"):
            raise ProviderError(
                f"Selected offering no longer present: {plan.offering_name}.")
        return raw

    def execute_hire(self, record: JobRecord, plan_dict: dict[str, Any]) -> ProviderJob:
        """Create exactly one ACP job from a frozen HirePlan.

        Runs final preflight, then issues a single create-offering-job bridge
        call against the plan's wallet, offering, and requirementData. Never
        rediscovers and never substitutes the seller.
        """
        from prior import hiring as hiring_mod

        self._require_ready()
        plan = hiring_mod.HirePlan.from_dict(plan_dict or {})
        violations = hiring_mod.validate_preflight(record, plan)
        if violations:
            raise hiring_mod.HireError(
                "Hire preflight refused the write: " + " | ".join(violations))
        raw = _bridge([
            "create-offering-job",
            plan.provider_wallet,
            plan.offering_name,
            json.dumps(plan.requirement_data),
        ])
        try:
            chain_id = int(raw.get("chainId"))
        except (TypeError, ValueError):
            chain_id = -1
        from prior.marketplace import SUPPORTED_CHAIN_ID

        if chain_id != SUPPORTED_CHAIN_ID:
            raise hiring_mod.AmbiguousHireError(
                "ACP create returned an unexpected execution chain "
                f"({raw.get('chainId')}); refusing to assume success. Reconcile first.")
        job_id = raw.get("jobId")
        if not job_id:
            raise ProviderError(f"ACP create-offering-job returned no jobId: {raw}")
        offer = AgentOffer(
            id=plan.provider_wallet,
            name=plan.agent_name or "Virtuals ACP agent",
            summary=f"Selected offering: {plan.offering_name}",
            price_label=str(plan.price_value) if plan.price_value is not None else "",
            source=VIRTUALS_SOURCE,
            network="Virtuals ACP",
            wallet_address=plan.provider_wallet,
            offering_name=plan.offering_name,
        )
        return ProviderJob(
            source=VIRTUALS_SOURCE,
            phase=str(raw.get("phase") or "job.created"),
            offer=offer,
            requirement=dict(plan.requirement_data),
            acp_job_id=str(job_id),
        )

    def execute_fund(self, record: JobRecord) -> dict[str, Any]:
        """Fund the job's seller-proposed budget: exactly one bridge call.

        Thin by design: all policy lives in service/hiring preflight. The
        bridge funds the on-chain proposed budget for this ACP job id only.
        """
        self._require_ready()
        if not record.acp_job_id:
            raise ProviderError("Cannot fund: missing ACP job id.")
        raw = _bridge(["fund", str(record.acp_job_id)])
        if not isinstance(raw, dict) or raw.get("ok") is not True:
            raise ProviderError(f"ACP fund returned failure: {raw}")
        return raw


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
        text=False,
        env=env,
        timeout=180,
        check=False,
    )
    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
    if proc.returncode != 0:
        detail = (stderr or stdout or "ACP bridge failed").strip()
        raise ProviderError(detail)
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"ACP bridge returned non-JSON: {stdout[:500]}") from exc


def _decode_deliverable(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
        return {"type": "text", "value": {"text": value}}
    return {"type": "text", "value": {"text": str(value)}}
