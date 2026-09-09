"""Dynamic-marketplace hire transactions: frozen HirePlan plus preflight.

A HirePlan freezes the selected transaction intent BEFORE any ACP write so
selection and execution cannot drift apart (no rediscovery, no seller
substitution). The ACP writer receives a HirePlan and must not discover
independently. Final preflight revalidates everything immediately before
the irreversible create call, including a semantic contract-loss guard:
if the improved contract cannot be faithfully expressed in the selected
offering's executable input, the write is refused.

Idempotency states live on the logical job (hire_state): prepared (plan
frozen, no write) -> creating (write attempted) -> created (external ACP
job id recorded) | failed (terminal attempt, re-preparable). Existing
job statuses are preserved unchanged.

Recovery boundary (documented limitation): if the ACP create succeeds
remotely but local persistence fails, PRIOR cannot correlate a later
lookup (the registry exposes no buyer idempotency key), so it records the
external id in a process-local registry and refuses blind retries with
AmbiguousHireError. An operator must reconcile via ACP history before any
manual retry. This is fail-safe, not silent.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from prior.domain import Contract, JobRecord, JobSpec
from prior.marketplace import (
    SUPPORTED_CHAIN_ID,
    MarketplaceCandidate,
    MarketplaceSelection,
    validate_against_schema,
)
from prior.providers.base import ProviderError


class HireError(ProviderError):
    """Hire-plan or preflight refusal. No write was attempted."""


class AmbiguousHireError(ProviderError):
    """A previous create may have succeeded remotely while local persistence
    is uncertain. Retrying blindly could create a second paid job, so PRIOR
    refuses. Reconcile via ACP job history before any manual retry."""


# In-process record of externally created jobs: logical job id -> ACP job
# id. Protects the double-click boundary when local persistence fails after
# a remote success. Does not survive restarts (documented limitation).
_COMPLETED_WRITES: dict[str, str] = {}


def note_completed_write(logical_job_id: str, acp_job_id: str) -> None:
    _COMPLETED_WRITES[str(logical_job_id)] = str(acp_job_id)


def completed_write_for(logical_job_id: str) -> str | None:
    return _COMPLETED_WRITES.get(str(logical_job_id))


def contract_fingerprint(contract: Contract) -> str:
    canonical = json.dumps(contract.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class HirePlan:
    """Frozen transaction intent for exactly one ACP job creation."""

    idempotency_key: str
    workspace_id: str
    logical_job_id: str
    agent_id: str
    agent_name: str
    provider_wallet: str
    offering_name: str
    chain_ids: list[str | int] = field(default_factory=list)
    price_type: str = ""
    price_value: float | str | None = None
    required_funds: bool = False
    requirements_schema: Any = None
    requirement_data: dict[str, Any] = field(default_factory=dict)
    learned_requirements: list[str] = field(default_factory=list)
    contract_fingerprint: str = ""
    marketplace_query: dict[str, Any] = field(default_factory=dict)
    selection_evidence: dict[str, Any] = field(default_factory=dict)
    selection_method: str = "marketplace-compatibility-v1"
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "idempotency_key": self.idempotency_key,
            "workspace_id": self.workspace_id,
            "logical_job_id": self.logical_job_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "provider_wallet": self.provider_wallet,
            "offering_name": self.offering_name,
            "chain_ids": list(self.chain_ids),
            "price_type": self.price_type,
            "price_value": self.price_value,
            "required_funds": self.required_funds,
            "requirements_schema": self.requirements_schema,
            "requirement_data": dict(self.requirement_data),
            "learned_requirements": list(self.learned_requirements),
            "contract_fingerprint": self.contract_fingerprint,
            "marketplace_query": dict(self.marketplace_query),
            "selection_evidence": dict(self.selection_evidence),
            "selection_method": self.selection_method,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HirePlan":
        return cls(
            idempotency_key=str(data.get("idempotency_key") or ""),
            workspace_id=str(data.get("workspace_id") or ""),
            logical_job_id=str(data.get("logical_job_id") or ""),
            agent_id=str(data.get("agent_id") or ""),
            agent_name=str(data.get("agent_name") or ""),
            provider_wallet=str(data.get("provider_wallet") or ""),
            offering_name=str(data.get("offering_name") or ""),
            chain_ids=list(data.get("chain_ids") or []),
            price_type=str(data.get("price_type") or ""),
            price_value=data.get("price_value"),
            required_funds=bool(data.get("required_funds", False)),
            requirements_schema=data.get("requirements_schema"),
            requirement_data=dict(data.get("requirement_data") or {}),
            learned_requirements=[str(item) for item in (data.get("learned_requirements") or [])],
            contract_fingerprint=str(data.get("contract_fingerprint") or ""),
            marketplace_query=dict(data.get("marketplace_query") or {}),
            selection_evidence=dict(data.get("selection_evidence") or {}),
            selection_method=str(data.get("selection_method") or ""),
            created_at=str(data.get("created_at") or ""),
        )


def build_hire_plan(record: JobRecord, selection: MarketplaceSelection) -> HirePlan:
    """Freeze a marketplace selection into a HirePlan. No writes occur."""
    candidate: MarketplaceCandidate = selection.candidate
    fingerprint = contract_fingerprint(record.contract)
    key_material = "|".join([
        record.workspace_id, record.id, fingerprint,
        candidate.wallet_address, candidate.offering_name or "",
    ])
    key = "hire_" + hashlib.sha256(key_material.encode("utf-8")).hexdigest()[:24]
    preview = selection.requirement_preview
    return HirePlan(
        idempotency_key=key,
        workspace_id=record.workspace_id,
        logical_job_id=record.id,
        agent_id=candidate.agent_id,
        agent_name=candidate.agent_name,
        provider_wallet=candidate.wallet_address,
        offering_name=candidate.offering_name or "",
        chain_ids=list(candidate.chain_ids),
        price_type=candidate.price_type,
        price_value=candidate.price_value,
        required_funds=candidate.required_funds,
        requirements_schema=candidate.requirements_schema,
        requirement_data=dict(preview.get("requirement_data") or {}),
        learned_requirements=list(preview.get("learned_requirements") or []),
        contract_fingerprint=fingerprint,
        marketplace_query=dict(selection.query.to_dict()),
        selection_evidence={
            "score": selection.score,
            "score_breakdown": dict(selection.score_breakdown),
            "task_evidence": [dict(item) for item in candidate.task_evidence],
            "subject_evidence": [dict(item) for item in candidate.subject_evidence],
            "schema_notes": list(candidate.schema_notes),
            "compatible_total": selection.compatible_total,
            "agents_seen": selection.agents_seen,
        },
        created_at=_now_iso(),
    )


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _executable_blob(requirement_data: dict[str, Any]) -> str:
    parts: list[str] = []

    def _walk(value: Any) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                _walk(item)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(requirement_data)
    return _normalize_text(" ".join(parts))


def validate_preflight(record: JobRecord, plan: HirePlan) -> list[str]:
    """Revalidate a frozen HirePlan immediately before any ACP write.

    Returns violations (empty = pass). Performs no writes and no discovery.
    """
    violations: list[str] = []
    if not plan.provider_wallet or not plan.provider_wallet.startswith("0x"):
        violations.append("A. provider identity missing: no seller wallet address.")
    if not plan.offering_name:
        violations.append("B. offering identity missing: no offering name.")
    chain_ids = []
    for cid in plan.chain_ids or []:
        try:
            chain_ids.append(int(cid))
        except (TypeError, ValueError):
            continue
    if SUPPORTED_CHAIN_ID not in chain_ids:
        violations.append("C. Base 8453 not in the selected offering chain path.")
    if plan.required_funds:
        violations.append("D. offering requires fund-transfer flow not yet supported by PRIOR.")
    try:
        from prior import settings as settings_mod
        price_max = settings_mod.max_acp_job_price_usdc()
    except ValueError as exc:
        return violations + [f"E. price policy misconfigured: {exc}"]
    price_type = str(plan.price_type or "")
    price_value = plan.price_value
    if price_type != "fixed" or not isinstance(price_value, (int, float)) or isinstance(price_value, bool):
        violations.append("E. price metadata missing, malformed, or unsupported (fixed USDC only).")
    elif not (0 <= float(price_value) <= price_max):
        violations.append(
            f"E. price {price_value} outside the configured max {price_max} USDC.")
    schema = plan.requirements_schema
    if schema not in (None, "", {}):
        problems = validate_against_schema(plan.requirement_data, schema)
        if problems:
            violations.append(
                "F. requirementData fails the selected offering schema: " + "; ".join(problems[:3]))
    blob = _executable_blob(plan.requirement_data)
    required_statements = list(plan.learned_requirements or []) + list(record.contract.acceptance or [])
    for statement in required_statements:
        text = _normalize_text(statement)
        if text and text not in blob:
            violations.append(
                "G. contract requirement not expressible in provider input: "
                + (text[:120] + ("..." if len(text) > 120 else "")))
    if record.workspace_id != plan.workspace_id or record.id != plan.logical_job_id:
        violations.append("H. plan does not belong to this logical job/workspace.")
    if record.acp_job_id:
        violations.append("I. logical job already has an external ACP execution id.")
    stored = record.hire_plan or {}
    if stored.get("idempotency_key") != plan.idempotency_key:
        violations.append("J. plan does not match the stored hire intent (possible substitution).")
    if plan.selection_method != "marketplace-compatibility-v1":
        violations.append("K. plan was not produced by the accepted compatibility path.")
    if plan.contract_fingerprint != contract_fingerprint(record.contract):
        violations.append("K2. contract changed after the plan was frozen; re-prepare required.")
    return violations
