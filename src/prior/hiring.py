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
    BRIEF_SLOTS,
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

# In-process supplement for ambiguous outcomes whose durable persist failed.
# Checked at execute start alongside the stored hire_state. The stored state
# remains primary; this only covers persist-failure windows.
_AMBIGUOUS_JOBS: set[str] = set()


def note_completed_write(logical_job_id: str, acp_job_id: str) -> None:
    _COMPLETED_WRITES[str(logical_job_id)] = str(acp_job_id)


def completed_write_for(logical_job_id: str) -> str | None:
    return _COMPLETED_WRITES.get(str(logical_job_id))


def mark_ambiguous(logical_job_id: str) -> None:
    _AMBIGUOUS_JOBS.add(str(logical_job_id))


def is_ambiguous(logical_job_id: str) -> bool:
    return str(logical_job_id) in _AMBIGUOUS_JOBS


def contract_fingerprint(contract: Contract) -> str:
    canonical = json.dumps(contract.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def expiry_state(expired_at: Any, now: float | None = None) -> str:
    """Deadline truth: 'expired', 'active', or 'unknown'.

    'unknown' (missing/malformed deadline) is never presented as expired,
    but funding guards treat anything but explicit 'active' as unfundable.
    """
    import time as _time

    try:
        deadline = int(str(expired_at).strip())
    except (TypeError, ValueError, AttributeError):
        return "unknown"
    if deadline <= 0:
        return "unknown"
    moment = now if now is not None else _time.time()
    return "expired" if moment > deadline else "active"


def describe_lifecycle(record: JobRecord) -> str:
    """PRIOR-level lifecycle for display. Never rewrites external ACP state.

    A hired/working job past its deadline reports 'expired' even while raw
    ACP still says OPEN (the chain does not auto-flip state). All other
    statuses report themselves.
    """
    if record.status in ("hired", "working"):
        if expiry_state(record.acp_expired_at) == "expired":
            return "expired"
        return "active"
    return record.status


def ensure_fundable(record: JobRecord) -> None:
    """Funding precondition: only an explicitly unexpired live job may fund.

    Unknown deadlines fail closed. Raises HireError otherwise.
    """
    if record.status not in ("hired", "working"):
        raise HireError(f"job {record.id} is not in a fundable lifecycle state.")
    if expiry_state(record.acp_expired_at) != "active":
        raise HireError(
            "the ACP deadline is passed or unknown. "
            "An expired job must not be funded.")


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
    brief_text: str = ""
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
            "brief_text": self.brief_text,
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
            brief_text=str(data.get("brief_text") or ""),
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
    from prior.providers.base import requirement_payload as _requirement_payload

    brief = ""
    try:
        brief = str(_requirement_payload(record.contract, record.spec).get("job_description") or "")
    except Exception:  # noqa: BLE001 - brief is presentational; gates use requirement_data
        brief = ""
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
        brief_text=brief,
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


def _canonical_schema(schema: Any) -> str:
    """Canonical form for drift comparison. Unparseable stays distinct."""
    if schema is None or schema == "" or schema == {}:
        return ""
    if isinstance(schema, str):
        try:
            import json as _json
            schema = _json.loads(schema)
        except ValueError:
            return "unparseable:" + str(schema)[:200]
    try:
        return json.dumps(schema, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return "unparseable:" + str(schema)[:200]


def verify_freshness(record: JobRecord, plan: HirePlan,
                     current: dict[str, Any]) -> list[str]:
    """Compare a live offering refresh against the frozen plan.

    Read-only. Any material drift refuses the write with a message telling
    the user to review a new plan. This is not rediscovery: the provider is
    never switched, only revalidated or refused.
    """
    drift: list[str] = []
    if not current.get("found") or not current.get("offering"):
        return ["Selected Virtuals offering changed: provider or offering no longer present. "
                "Please review the updated hire plan."]
    try:
        buyer_chain = int(current.get("chainId"))
    except (TypeError, ValueError):
        buyer_chain = -1
    if buyer_chain != SUPPORTED_CHAIN_ID:
        # Definitive pre-write refusal: the ACTUAL buyer SDK execution chain
        # is wrong, regardless of what the provider advertises. No write.
        return [f"Buyer execution network mismatch: live buyer chain is "
                f"{current.get('chainId')}, PRIOR requires Base {SUPPORTED_CHAIN_ID}. "
                "Correct configuration and prepare again."]
    offering = current["offering"] or {}
    if offering.get("isHidden") or offering.get("isPrivate"):
        drift.append("Selected offering is now hidden or private.")
    chain_ids = []
    for cid in current.get("chains") or []:
        try:
            chain_ids.append(int(cid))
        except (TypeError, ValueError):
            continue
    if SUPPORTED_CHAIN_ID not in chain_ids:
        drift.append("Selected offering left the supported Base 8453 path.")
    if bool(offering.get("requiredFunds", False)) is True:
        drift.append("Selected offering now requires a fund-transfer flow PRIOR does not support.")
    if str(offering.get("priceType") or "") != str(plan.price_type or ""):
        drift.append(f"Offering price type changed ({plan.price_type} -> {offering.get('priceType')}).")
    try:
        if float(offering.get("priceValue")) != float(plan.price_value or 0):
            drift.append(f"Offering price changed ({plan.price_value} -> {offering.get('priceValue')}).")
    except (TypeError, ValueError):
        drift.append("Offering price is no longer parseable.")
    if _canonical_schema(offering.get("requirements")) != _canonical_schema(plan.requirements_schema):
        drift.append("Offering requirements schema changed.")
    # Brief slot and learned-clause fit against the CURRENT schema.
    from prior.marketplace import BRIEF_SLOTS

    properties = None
    schema = offering.get("requirements")
    if isinstance(schema, str):
        try:
            import json as _json
            schema = _json.loads(schema)
        except ValueError:
            schema = None
    if isinstance(schema, dict):
        properties = schema.get("properties")
    if isinstance(properties, dict):
        slots = [name for name, sub in properties.items()
                 if isinstance(sub, dict) and _brief_slot_name(name)
                 and _accepts_brief_text(sub)]
        if not slots:
            drift.append("Current offering schema no longer has a field for the task brief.")
    elif schema not in (None, "", {}):
        drift.append("Current offering schema can no longer be interpreted.")
    try:
        from prior import settings as settings_mod
        price_max = settings_mod.max_acp_job_price_usdc()
    except ValueError as exc:
        return drift + [f"E. price policy misconfigured: {exc}"]
    try:
        current_price = float(offering.get("priceValue"))
    except (TypeError, ValueError):
        return drift + ["Current offering price is missing or malformed."]
    if str(offering.get("priceType") or "") != "fixed" or not (0 <= current_price <= price_max):
        drift.append(f"Current price fails the spend cap (max {price_max} USDC).")
    if drift:
        drift.append("Selected Virtuals offering changed. Please review the updated hire plan.")
    return drift


def _brief_slot_name(name: str) -> bool:
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum()) in BRIEF_SLOTS


def _accepts_brief_text(subschema: dict[str, Any]) -> bool:
    kind = subschema.get("type")
    if kind is None:
        return True
    kinds = [kind] if isinstance(kind, str) else list(kind)
    return "string" in kinds


def plan_presentation(plan: HirePlan) -> dict[str, Any]:
    """Truthful confirmation content for the user: what is about to happen."""
    evidence = plan.selection_evidence or {}
    breakdown = evidence.get("score_breakdown") or {}
    task_evidence = evidence.get("task_evidence") or []
    price_text = "unpriced"
    if str(plan.price_type or "") == "fixed" and isinstance(plan.price_value, (int, float)):
        price_text = f"{plan.price_value} USDC"
    match_bits = []
    for item in task_evidence:
        if isinstance(item, dict) and item.get("capability"):
            match_bits.append(f"{item['capability']} ({item.get('source', '?')})")
    return {
        "agent": plan.agent_name,
        "offering": plan.offering_name,
        "network": "Virtuals ACP",
        "price": price_text,
        "match_reason": f"score {evidence.get('score')}; " + (
            ", ".join(match_bits) if match_bits else "marketplace compatibility gates"),
        "remembered": list(plan.learned_requirements or []),
        "will_be_sent": (plan.brief_text or "")[:800],
        "requirement_data": dict(plan.requirement_data or {}),
        "idempotency_key": plan.idempotency_key,
    }


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


# ---------------------------------------------------------------------------
# Explicit user-approved funding. The standard ACP lifecycle requires the
# buyer to escrow the seller-proposed budget (session.fund() funds the job's
# budget); requiredFunds=false means no ADDITIONAL transfer flow, not that
# funding is unnecessary. Funding is a real write: frozen intent, preflight,
# atomic claim, single bridge call, durable ambiguous state on uncertainty.
# ---------------------------------------------------------------------------

# Currency basis: the SDK settles in USDC (AssetToken.usdc, USDC_ADDRESSES;
# official FAQ prices jobs like "$0.01"). Only this exact token is accepted.
USDC_BASE_ADDRESSES = {8453: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"}


@dataclass
class FundIntent:
    """Frozen funding intent for exactly one fund execution."""

    idempotency_key: str
    workspace_id: str
    logical_job_id: str
    acp_job_id: str
    provider_wallet: str
    amount: float
    currency: str
    token_address: str
    chain_id: int
    contract_fingerprint: str
    hire_key: str
    budget_snapshot: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "idempotency_key": self.idempotency_key,
            "workspace_id": self.workspace_id,
            "logical_job_id": self.logical_job_id,
            "acp_job_id": self.acp_job_id,
            "provider_wallet": self.provider_wallet,
            "amount": self.amount,
            "currency": self.currency,
            "token_address": self.token_address,
            "chain_id": self.chain_id,
            "contract_fingerprint": self.contract_fingerprint,
            "hire_key": self.hire_key,
            "budget_snapshot": dict(self.budget_snapshot),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FundIntent":
        try:
            amount = float(data.get("amount"))
        except (TypeError, ValueError):
            amount = -1.0
        try:
            chain_id = int(data.get("chain_id"))
        except (TypeError, ValueError):
            chain_id = -1
        return cls(
            idempotency_key=str(data.get("idempotency_key") or ""),
            workspace_id=str(data.get("workspace_id") or ""),
            logical_job_id=str(data.get("logical_job_id") or ""),
            acp_job_id=str(data.get("acp_job_id") or ""),
            provider_wallet=str(data.get("provider_wallet") or ""),
            amount=amount,
            currency=str(data.get("currency") or ""),
            token_address=str(data.get("token_address") or ""),
            chain_id=chain_id,
            contract_fingerprint=str(data.get("contract_fingerprint") or ""),
            hire_key=str(data.get("hire_key") or ""),
            budget_snapshot=dict(data.get("budget_snapshot") or {}),
            created_at=str(data.get("created_at") or ""),
        )


def _budget_amount(budget: dict[str, Any] | None) -> float | None:
    if not isinstance(budget, dict):
        return None
    try:
        value = float(budget.get("amount"))
    except (TypeError, ValueError):
        return None
    return value


def build_fund_intent(record: JobRecord, budget: dict[str, Any],
                      chain_id: int) -> FundIntent:
    """Freeze a funding intent from live budget evidence. No writes occur."""
    amount = _budget_amount(budget)
    key_material = "|".join([
        record.workspace_id, record.id, str(record.acp_job_id),
        str(amount), str(budget.get("tokenAddress") or ""), str(chain_id),
        contract_fingerprint(record.contract),
    ])
    key = "fund_" + hashlib.sha256(key_material.encode("utf-8")).hexdigest()[:24]
    provider = record.provider or {}
    return FundIntent(
        idempotency_key=key,
        workspace_id=record.workspace_id,
        logical_job_id=record.id,
        acp_job_id=str(record.acp_job_id or ""),
        provider_wallet=str(provider.get("wallet_address") or ""),
        amount=amount if amount is not None else -1.0,
        currency=str(budget.get("symbol") or ""),
        token_address=str(budget.get("tokenAddress") or ""),
        chain_id=int(chain_id),
        contract_fingerprint=contract_fingerprint(record.contract),
        hire_key=str((record.hire_plan or {}).get("idempotency_key") or ""),
        budget_snapshot=dict(budget),
        created_at=_now_iso(),
    )


def validate_fund_preflight(record: JobRecord, intent: FundIntent,
                            current: dict[str, Any]) -> list[str]:
    """Revalidate a frozen funding intent immediately before any fund write.

    Returns violations (empty = pass). Performs no writes and no discovery.
    Amount rule: 0 < current ≤ approved frozen price (when known) and ≤
    configured max. A lower seller budget is honored as proposed; a higher
    one is refused. Currency must be the exact USDC token on Base 8453.
    """
    violations: list[str] = []
    if record.workspace_id != intent.workspace_id or record.id != intent.logical_job_id:
        violations.append("fund intent does not belong to this logical job/workspace.")
    if not record.acp_job_id or record.acp_job_id != intent.acp_job_id:
        violations.append("fund intent targets a different ACP job.")
    if record.status not in ("hired", "working"):
        violations.append("job is not in a fundable lifecycle state.")
    try:
        ensure_fundable(record)
    except HireError as exc:
        violations.append(f"funding refused: {exc}")
    if current.get("funded") is True or current.get("sessionStatus") == "funded":
        violations.append("job is already funded; double-funding refused.")
    live_budget = current.get("budget") if isinstance(current.get("budget"), dict) else None
    live_amount = _budget_amount(live_budget)
    if live_amount is None or not (live_amount > 0):
        violations.append("no positive live seller budget to fund.")
    else:
        if abs(live_amount - intent.amount) > 1e-9:
            violations.append(
                f"seller budget drifted ({intent.amount} -> {live_amount}); re-prepare required.")
        token = str((live_budget or {}).get("tokenAddress") or "")
        expected_token = USDC_BASE_ADDRESSES.get(SUPPORTED_CHAIN_ID, "")
        if token.lower() != expected_token.lower():
            violations.append("budget token is not the supported USDC settlement token.")
        try:
            live_chain = int(current.get("chainId"))
        except (TypeError, ValueError):
            live_chain = -1
        if live_chain != SUPPORTED_CHAIN_ID:
            violations.append("budget job is not on the supported Base 8453 path.")
        if str((live_budget or {}).get("symbol") or "").upper() != "USDC":
            violations.append("budget currency is not USDC.")
    approved = None
    plan_price = (record.hire_plan or {}).get("price_value")
    try:
        approved = float(plan_price) if plan_price is not None else None
    except (TypeError, ValueError):
        approved = None
    try:
        from prior import settings as settings_mod
        price_max = settings_mod.max_acp_job_price_usdc()
    except ValueError as exc:
        return violations + [f"price policy misconfigured: {exc}"]
    if live_amount is not None and live_amount > 0:
        if approved is not None and live_amount > approved + 1e-9:
            violations.append(
                f"seller budget {live_amount} exceeds the approved hire price {approved}.")
        if not (live_amount <= price_max):
            violations.append(f"seller budget {live_amount} exceeds the spend cap {price_max} USDC.")
    stored = record.fund_intent or {}
    if stored and stored.get("idempotency_key") != intent.idempotency_key:
        violations.append("fund intent does not match the stored funding intent (possible substitution).")
    if intent.contract_fingerprint != contract_fingerprint(record.contract):
        violations.append("contract changed after funding was prepared; re-prepare required.")
    return violations


def fund_presentation(intent: FundIntent, record: JobRecord) -> dict[str, Any]:
    """Truthful confirmation content: what funding is about to do."""
    provider = record.provider or {}
    return {
        "agent": provider.get("name") or "Virtuals ACP agent",
        "offering": provider.get("offering_name") or "",
        "network": "Virtuals ACP",
        "amount": intent.amount,
        "currency": intent.currency or "USDC",
        "acp_job_id": intent.acp_job_id,
        "expiry": describe_lifecycle(record),
        "idempotency_key": intent.idempotency_key,
    }
