"""Core PRIOR loop: normalize, recall, contract, hire, evaluate, persist lessons."""

from __future__ import annotations

import uuid
from typing import Any

from prior import jobs
from prior.contract import build_contract, unavailable_contract
from prior.domain import JobRecord, Lesson, SUPPORTED_JOB_TYPE
from prior.job_spec import parse_job
from prior.lessons import applicable_lessons, is_duplicate, now_iso, propose_lesson, sanitize_payload
from prior.memory import (
    MEMORY_UNAVAILABLE,
    MemoryUnavailable,
    disable_lesson,
    list_lessons,
    open_memory,
    recall_lessons,
    write_lesson,
)
from prior.providers import active_provider, provider_for_record
from prior.providers.base import ProviderError, ProviderJob, requirement_payload
from prior.providers.local import LOCAL_SOURCE

_OPEN_JOB_STATUSES = {"specified", "hired", "working"}


def new_ids() -> str:
    return "job_" + uuid.uuid4().hex[:12]


def specify(workspace_id: str, raw: str) -> JobRecord:
    existing = _reusable_job(workspace_id, raw)
    if existing is not None:
        return existing
    spec = parse_job(raw)
    memory_status = "ok"
    memory_message = None
    lessons: list[Lesson] = []
    try:
        open_memory(workspace_id)
        if spec.job_type == SUPPORTED_JOB_TYPE:
            candidates = recall_lessons(workspace_id, spec.raw, spec.keywords + [spec.domain, spec.job_type])
            lessons = applicable_lessons(spec, candidates)
            if not lessons:
                memory_message = "No relevant lessons found. Starting with standard requirements."
    except MemoryUnavailable:
        memory_status = "unavailable"
        memory_message = MEMORY_UNAVAILABLE

    if memory_status == "unavailable":
        contract = unavailable_contract(spec)
    else:
        contract = build_contract(
            spec,
            lessons,
            memory_status=memory_status,
            memory_message=memory_message,
        )

    record = JobRecord(
        id=new_ids(),
        workspace_id=workspace_id,
        spec=spec,
        contract=contract,
        status="refused" if spec.job_type != SUPPORTED_JOB_TYPE else "specified",
        created_at=now_iso(),
        updated_at=now_iso(),
        error=spec.refusal_reason if spec.job_type != SUPPORTED_JOB_TYPE else None,
    )
    return jobs.put(record)


def hire(workspace_id: str, job_id: str) -> JobRecord:
    """Historical fixed-path hire (first offer wins).

    Preserved for backward compatibility and existing tests. The dynamic
    marketplace path is prepare_hire + execute_hire, which selects a live
    offering and freezes it in a HirePlan before any write.
    """
    record = _owned(workspace_id, job_id)
    if record.status == "refused":
        raise ValueError(record.error or "This job is outside the research domain.")
    if record.status in {"hired", "working"}:
        return refresh(workspace_id, job_id)
    if record.status in {"delivered", "accepted", "rejected"}:
        return record
    if record.contract.memory_status == "unavailable":
        raise MemoryUnavailable(MEMORY_UNAVAILABLE)
    provider = active_provider()
    offers = provider.find_providers(record.spec)
    offer = offers[0]
    started = provider.create_job(offer, record.contract, record.spec)
    return _apply_provider_job(record, started)


def prepare_hire(workspace_id: str, job_id: str, discover=None) -> dict[str, Any]:
    """Dynamic path, phase 1 (read-only): select a live offering and freeze a
    HirePlan on the logical job. No ACP write occurs. Idempotent: re-preparing
    an already-prepared job with an unchanged contract returns the stored plan.
    """
    from prior import hiring as hiring_mod
    from prior.providers.virtuals import VirtualsAcpProvider

    record = _owned(workspace_id, job_id)
    if record.status == "refused":
        raise ValueError(record.error or "This job is outside the research domain.")
    if record.status in {"hired", "working", "delivered", "accepted", "rejected"}:
        raise ValueError(f"Job {job_id} already left the specified state; cannot prepare a hire.")
    if record.contract.memory_status == "unavailable":
        raise MemoryUnavailable(MEMORY_UNAVAILABLE)
    if record.hire_state == "creating":
        raise hiring_mod.AmbiguousHireError(
            "A hire is already in progress for this job; refusing a second intent.")
    if record.hire_state == "ambiguous" or hiring_mod.is_ambiguous(record.id):
        raise hiring_mod.AmbiguousHireError(
            "A previous hire outcome is ambiguous; reconcile before preparing again.")
    if record.hire_state == "created" or record.acp_job_id:
        raise ValueError("Job already has an ACP execution; cannot prepare another hire.")
    if record.hire_state == "prepared" and record.hire_plan:
        existing = hiring_mod.HirePlan.from_dict(record.hire_plan)
        if existing.contract_fingerprint == hiring_mod.contract_fingerprint(record.contract):
            return record.hire_plan
    blocker = hiring_mod.blocking_paid_job(record.workspace_id, record.id)
    if blocker is not None:
        raise ValueError(
            "Another paid ACP job in this workspace is still active "
            f"({blocker.id}); finish or wait for it before preparing another paid hire.")
    provider = VirtualsAcpProvider()
    plan_dict = provider.prepare_hire(record, discover=discover)
    record.hire_plan = plan_dict
    record.hire_state = "prepared"
    record.hire_error = None
    record.updated_at = now_iso()
    jobs.put(record)
    return plan_dict


def execute_hire(workspace_id: str, job_id: str) -> JobRecord:
    """Dynamic path, phase 2: create exactly one ACP job from the frozen plan.

    Order: load -> idempotency guards -> writes gate -> read-only preflight
    -> read-only freshness revalidation -> atomic claim -> re-read -> single
    bridge create. Any uncertain failure after the write boundary leaves a
    durable ambiguous state (never retryable `failed`); only definitive
    pre-write refusals stay retryable.
    """
    from prior import hiring as hiring_mod
    from prior.providers.virtuals import VirtualsAcpProvider

    record = _owned(workspace_id, job_id)
    if record.hire_state == "created" and record.acp_job_id:
        return record
    if (record.hire_state in ("creating", "ambiguous")
            or hiring_mod.completed_write_for(record.id)
            or hiring_mod.is_ambiguous(record.id)):
        raise hiring_mod.AmbiguousHireError(
            "A previous hire may have created an ACP job while local persistence "
            "is uncertain. Reconcile via ACP job history before any manual retry; "
            "PRIOR will not blindly create a second job.")
    if record.hire_state != "prepared" or not record.hire_plan:
        raise ValueError("No prepared hire intent for this job; prepare first.")
    if record.status != "specified":
        raise ValueError("Job left the specified state after preparation; prepare again if still needed.")
    from prior import settings as settings_mod

    if not settings_mod.acp_writes_enabled():
        raise ProviderError(
            "ACP writes are disabled by server configuration (PRIOR_ENABLE_ACP_WRITES).")
    provider = VirtualsAcpProvider()
    plan = hiring_mod.HirePlan.from_dict(record.hire_plan)
    violations = hiring_mod.validate_preflight(record, plan)
    if violations:
        _fail_hire(record, "Hire preflight refused the write: " + " | ".join(violations))
        raise hiring_mod.HireError(
            "Hire preflight refused the write: " + " | ".join(violations))
    try:
        current = provider.refresh_selected_offering(record.hire_plan)
    except ProviderError as exc:
        raise ProviderError(f"Could not verify offering freshness: {exc}") from exc
    drift = hiring_mod.verify_freshness(record, plan, current)
    if drift:
        _fail_hire(record, " | ".join(drift))
        raise hiring_mod.HireError(" | ".join(drift))
    try:
        record = jobs.hire_claim(record.id, record.workspace_id)
    except jobs.HireConflictError:
        return _resolve_claim_conflict(workspace_id, job_id)
    except KeyError:
        raise
    try:
        started = provider.execute_hire(record, record.hire_plan or {})
    except hiring_mod.AmbiguousHireError:
        raise
    except Exception as exc:
        try:
            _ambiguous_hire(record, f"Uncertain ACP create result: {exc}")
        except hiring_mod.AmbiguousHireError:
            raise
        except Exception:
            hiring_mod.mark_ambiguous(record.id)
        raise hiring_mod.AmbiguousHireError(
            f"Uncertain ACP create result ({exc}). State is durably ambiguous; "
            "reconcile via ACP job history before any manual retry.") from exc
    hiring_mod.note_completed_write(record.id, started.acp_job_id or "")
    try:
        record = _apply_provider_job(record, started)
        record.hire_state = "created"
        record.hire_error = None
        jobs.put(record)
    except Exception as exc:
        hiring_mod.mark_ambiguous(record.id)
        raise hiring_mod.AmbiguousHireError(
            "ACP job was created remotely but the local record could not be "
            f"persisted ({exc}). Do not retry blindly; reconcile first.") from exc
    return record


def _fail_hire(record: JobRecord, message: str) -> None:
    """Definitive pre-write refusal: retryable via a fresh prepare."""
    record.hire_state = "failed"
    record.hire_error = message[:500]
    record.updated_at = now_iso()
    jobs.put(record)


def _ambiguous_hire(record: JobRecord, message: str) -> None:
    """Uncertain post-boundary outcome: durable, never auto-retryable."""
    from prior import hiring as hiring_mod

    record.hire_state = "ambiguous"
    record.hire_error = message[:500]
    record.updated_at = now_iso()
    try:
        jobs.put(record)
    except Exception:
        hiring_mod.mark_ambiguous(record.id)
        raise
    hiring_mod.mark_ambiguous(record.id)


def _resolve_claim_conflict(workspace_id: str, job_id: str) -> JobRecord:
    """Lost an atomic claim race: return the winner's job if it completed."""
    from prior import hiring as hiring_mod

    record = _owned(workspace_id, job_id)
    if record.hire_state == "created" and record.acp_job_id:
        return record
    raise hiring_mod.AmbiguousHireError(
        "Another execution claimed this job concurrently. Re-read before retrying; "
        "PRIOR created no second job from this call.")


def _current_funding_status(record: JobRecord) -> dict[str, Any]:
    """Read-only funding observation: refresh without side effects."""
    from prior.providers.virtuals import VirtualsAcpProvider

    provider = VirtualsAcpProvider()
    current = _record_to_provider_job(record)
    updated = provider.get_job_status(current)
    return {
        "phase": updated.phase,
        "budget": updated.extra.get("budget") if isinstance(updated.extra.get("budget"), dict) else None,
        "funded": updated.extra.get("funded"),
        "sessionStatus": updated.extra.get("sessionStatus"),
        "chainId": updated.extra.get("chainId"),
    }


def prepare_fund(workspace_id: str, job_id: str) -> dict[str, Any]:
    """Funding path, phase 1 (read-only except local intent storage).

    Observes the live seller budget, verifies the job is actively fundable,
    and freezes a FundIntent. Issues no ACP writes (bridge calls: status).
    """
    from prior import hiring as hiring_mod

    record = _owned(workspace_id, job_id)
    if record.status not in ("hired", "working"):
        raise ValueError("Only a live hired job can be funded.")
    if record.fund_state == "funded":
        raise ValueError("Job is already funded; double-funding refused.")
    if (record.fund_state in ("funding", "fund_ambiguous")
            or hiring_mod.is_ambiguous(record.id)):
        raise hiring_mod.AmbiguousHireError(
            "A previous funding outcome is ambiguous; reconcile before preparing again.")
    if not record.acp_job_id:
        raise ValueError("Job has no external ACP execution to fund.")
    if record.fund_state == "fund_prepared" and record.fund_intent:
        existing = hiring_mod.FundIntent.from_dict(record.fund_intent)
        if existing.contract_fingerprint == hiring_mod.contract_fingerprint(record.contract):
            return hiring_mod.fund_presentation(existing, record)
    record = refresh(workspace_id, job_id)
    if record.status not in ("hired", "working"):
        raise ValueError("Only a live hired job can be funded.")
    current = _current_funding_status(record)
    budget = current.get("budget") or {}
    chain_id = current.get("chainId") or 8453
    intent = hiring_mod.build_fund_intent(record, budget, chain_id)
    violations = hiring_mod.validate_fund_preflight(record, intent, current)
    if violations:
        record.fund_state = "fund_failed"
        record.fund_error = " | ".join(violations)[:500]
        record.updated_at = now_iso()
        jobs.put(record)
        raise hiring_mod.HireError(
            "Funding preflight refused: " + " | ".join(violations))
    record.fund_intent = intent.to_dict()
    record.fund_state = "fund_prepared"
    record.fund_error = None
    record.updated_at = now_iso()
    jobs.put(record)
    return hiring_mod.fund_presentation(intent, record)


def execute_fund(workspace_id: str, job_id: str) -> JobRecord:
    """Funding path, phase 2: fund exactly the frozen intent, once.

    Revalidates against live state after an atomic claim. Uncertain
    post-boundary outcomes persist durably ambiguous and never auto-retry.
    """
    from prior import hiring as hiring_mod
    from prior.providers.virtuals import VirtualsAcpProvider

    record = _owned(workspace_id, job_id)
    if record.status not in ("hired", "working"):
        raise ValueError("Only a live hired job can be funded.")
    if record.fund_state == "funded":
        return record
    if (record.fund_state in ("funding", "fund_ambiguous")
            or hiring_mod.is_ambiguous(record.id)):
        raise hiring_mod.AmbiguousHireError(
            "A previous funding outcome is uncertain. Reconcile via ACP job "
            "history before any manual retry; PRIOR will not fund twice.")
    if record.fund_state != "fund_prepared" or not record.fund_intent:
        raise ValueError("No prepared funding intent for this job; prepare first.")
    record = refresh(workspace_id, job_id)
    if record.status not in ("hired", "working"):
        raise ValueError("Only a live hired job can be funded.")
    from prior import settings as settings_mod

    if not settings_mod.acp_writes_enabled():
        raise ProviderError(
            "ACP writes are disabled by server configuration (PRIOR_ENABLE_ACP_WRITES).")
    provider = VirtualsAcpProvider()
    intent = hiring_mod.FundIntent.from_dict(record.fund_intent)
    current = _current_funding_status(record)
    violations = hiring_mod.validate_fund_preflight(record, intent, current)
    if violations:
        record.fund_state = "fund_failed"
        record.fund_error = " | ".join(violations)[:500]
        record.updated_at = now_iso()
        jobs.put(record)
        raise hiring_mod.HireError(
            "Funding preflight refused: " + " | ".join(violations))
    try:
        record = jobs.fund_claim(record.id, record.workspace_id)
    except jobs.FundConflictError:
        resolved = _owned(workspace_id, job_id)
        if resolved.fund_state == "funded":
            return resolved
        raise hiring_mod.AmbiguousHireError(
            "Another funding claimed this job concurrently. Re-read before "
            "retrying; PRIOR funded nothing from this call.")
    except KeyError:
        raise
    try:
        result = provider.execute_fund(record)
    except hiring_mod.AmbiguousHireError:
        raise
    except Exception as exc:
        try:
            _ambiguous_fund(record, f"Uncertain ACP fund result: {exc}")
        except hiring_mod.AmbiguousHireError:
            raise
        except Exception:
            hiring_mod.mark_ambiguous(record.id)
        raise hiring_mod.AmbiguousHireError(
            f"Uncertain ACP fund result ({exc}). State is durably ambiguous; "
            "reconcile before any manual retry.") from exc
    record.fund_state = "funded"
    record.fund_error = None
    record.updated_at = now_iso()
    try:
        jobs.put(record)
    except Exception as exc:
        hiring_mod.mark_ambiguous(record.id)
        raise hiring_mod.AmbiguousHireError(
            "ACP fund succeeded remotely but local persistence failed "
            f"({exc}). Reconcile before retrying.") from exc
    return record


def _ambiguous_fund(record: JobRecord, message: str) -> None:
    """Uncertain post-boundary funding outcome: durable, never auto-retryable."""
    from prior import hiring as hiring_mod

    record.fund_state = "fund_ambiguous"
    record.fund_error = message[:500]
    record.updated_at = now_iso()
    try:
        jobs.put(record)
    except Exception:
        hiring_mod.mark_ambiguous(record.id)
        raise
    hiring_mod.mark_ambiguous(record.id)


def refresh(workspace_id: str, job_id: str) -> JobRecord:
    record = _owned(workspace_id, job_id)
    if record.status not in {"hired", "working"}:
        if not (
            record.status == "delivered"
            and record.evaluation is None
            and str((record.provider or {}).get("source") or "") != LOCAL_SOURCE
        ):
            return record
    if not record.provider:
        return record
    provider = provider_for_record(record)
    current = _record_to_provider_job(record)
    updated = provider.get_job_status(current)
    if updated.extra.get("expiredAt"):
        record.acp_expired_at = str(updated.extra["expiredAt"])
    if isinstance(updated.extra.get("budget"), dict):
        record.acp_budget = dict(updated.extra["budget"])
    if updated.extra.get("funded") is True and record.fund_state != "funded":
        record.fund_state = "funded"
        record.fund_error = None
    # Concurrency guard: this refresh loaded its snapshot before a slow
    # bridge call, so a prepare path may have persisted fund/hire intent
    # meanwhile. Refresh owns ACP observation fields only; never clobber
    # intent it did not create. Re-read freshest state and carry those
    # fields forward (the funded transition above is the one exception).
    latest = jobs.get(record.id, workspace_id)
    if latest is not None:
        if record.fund_state != "funded":
            record.fund_state = latest.fund_state
            record.fund_intent = latest.fund_intent
            record.fund_error = latest.fund_error
        record.hire_state = latest.hire_state
        record.hire_plan = latest.hire_plan
        record.hire_error = latest.hire_error
    return _apply_provider_job(record, updated)


def _attempt_remote_evaluation(record: JobRecord, accepted: bool, reason: str) -> str:
    """Best-effort marketplace evaluation. The human verdict is already
    persisted by the caller; this never raises and never claims a remote
    outcome that did not happen."""
    from prior import settings as settings_mod

    source = str((record.provider or {}).get("source") or "")
    if source == LOCAL_SOURCE:
        try:
            evaluated = provider_for_record(record).evaluate(
                _record_to_provider_job(record), accepted, reason
            )
        except Exception as exc:
            return f"local evaluation failed: {str(exc)[:160]}"
        record.acp_phase = evaluated.phase
        return "confirmed locally"
    if not settings_mod.acp_writes_enabled():
        return "not attempted (ACP writes disabled by server configuration)"
    if (record.acp_phase or "").lower() in {"expired", "job.expired"}:
        return "not attempted (ACP evaluation window expired)"
    try:
        evaluated = provider_for_record(record).evaluate(
            _record_to_provider_job(record), accepted, reason
        )
    except Exception as exc:
        return f"attempt failed: {str(exc)[:160]}"
    record.acp_phase = evaluated.phase
    if evaluated.extra.get("txHash"):
        record.tx_hash = str(evaluated.extra["txHash"])
    return "confirmed by ACP"


def accept(workspace_id: str, job_id: str) -> JobRecord:
    record = _owned(workspace_id, job_id)
    if record.status != "delivered":
        raise ValueError("Only a delivered job can be accepted.")
    record.evaluation = "accepted"
    record.status = "accepted"
    record.remote_evaluation = "pending"
    record.updated_at = now_iso()
    jobs.put(record)
    record.remote_evaluation = _attempt_remote_evaluation(
        record, True, "Accepted by the hiring user."
    )
    record.updated_at = now_iso()
    return jobs.put(record)


def reject(workspace_id: str, job_id: str, reason: str) -> JobRecord:
    record = _owned(workspace_id, job_id)
    if record.status != "delivered":
        raise ValueError("Only a delivered job can be rejected.")
    if not (reason or "").strip():
        raise ValueError("A rejection needs a useful reason.")
    record.evaluation = "rejected"
    record.rejection_reason = reason.strip()
    record.status = "rejected"
    record.proposed_lesson = propose_lesson(record, reason).to_dict()
    record.remote_evaluation = "pending"
    record.updated_at = now_iso()
    jobs.put(record)
    record.remote_evaluation = _attempt_remote_evaluation(
        record, False, reason.strip()
    )
    record.updated_at = now_iso()
    return jobs.put(record)


def decide_lesson(
    workspace_id: str,
    job_id: str,
    action: str,
    requirement: str | None = None,
    issue: str | None = None,
) -> JobRecord:
    record = _owned(workspace_id, job_id)
    if not record.proposed_lesson:
        raise ValueError("No lesson is waiting for approval.")
    payload = dict(record.proposed_lesson)
    if requirement:
        payload["requirement"] = requirement
    if issue:
        payload["issue"] = issue
    clean = sanitize_payload(payload)
    lesson = Lesson.from_dict(clean)

    if action == "ignore":
        record.proposed_lesson = {**payload, "status": "ignored"}
        record.updated_at = now_iso()
        return jobs.put(record)

    if action not in {"add", "edit"}:
        raise ValueError("Lesson action must be add, edit, or ignore.")

    existing = list_lessons(workspace_id)
    duplicate = is_duplicate(existing, lesson.requirement)
    if duplicate:
        record.proposed_lesson = {
            **lesson.to_dict(),
            "status": "duplicate",
            "existing_id": duplicate.id,
        }
        record.updated_at = now_iso()
        return jobs.put(record)

    lesson.provenance = "user-edited" if action == "edit" else "user-approved"
    lesson.status = "active"
    write_lesson(workspace_id, lesson)
    record.proposed_lesson = lesson.to_dict()
    record.updated_at = now_iso()
    return jobs.put(record)


def memory_view(workspace_id: str) -> dict[str, Any]:
    try:
        lessons = list_lessons(workspace_id)
    except MemoryUnavailable as exc:
        return {"status": "unavailable", "message": str(exc), "lessons": [], "jobs": []}
    return {
        "status": "ok",
        "lessons": [lesson.to_dict() for lesson in lessons],
        "count": len([item for item in lessons if item.status == "active"]),
        "jobs": [record.to_dict() for record in jobs.list_for(workspace_id)[:20]],
    }


def retire_lesson(workspace_id: str, lesson_id: str) -> dict[str, Any]:
    disable_lesson(workspace_id, lesson_id)
    return memory_view(workspace_id)


def _owned(workspace_id: str, job_id: str) -> JobRecord:
    record = jobs.get(job_id, workspace_id)
    if record is None:
        raise KeyError("Job not found in this workspace.")
    return record


def _apply_provider_job(record: JobRecord, started: ProviderJob) -> JobRecord:
    record.provider = started.offer.to_dict()
    record.acp_job_id = started.acp_job_id
    record.acp_phase = started.phase
    if record.worker_requirement is None:
        record.worker_requirement = started.requirement
    if started.extra.get("txHash"):
        record.tx_hash = str(started.extra["txHash"])
    if started.deliverable:
        record.deliverable = started.deliverable
        record.status = "delivered"
    elif started.source == LOCAL_SOURCE:
        record.status = "working"
    elif started.extra.get("submitted") is True:
        record.deliverable = None
        record.status = "delivered"
    else:
        record.status = "hired"
    record.error = started.error
    record.updated_at = now_iso()
    return jobs.put(record)


def _record_to_provider_job(record: JobRecord) -> ProviderJob:
    from prior.domain import AgentOffer

    offer_data = record.provider or {}
    offer = AgentOffer(
        id=str(offer_data.get("id") or ""),
        name=str(offer_data.get("name") or ""),
        summary=str(offer_data.get("summary") or ""),
        price_label=str(offer_data.get("price_label") or ""),
        source=str(offer_data.get("source") or ""),
        network=str(offer_data.get("network") or ""),
        wallet_address=offer_data.get("wallet_address"),
        offering_name=offer_data.get("offering_name"),
    )
    req = record.worker_requirement or requirement_payload(record.contract, record.spec)
    return ProviderJob(
        source=str(offer_data.get("source") or ""),
        phase=record.acp_phase or record.status,
        offer=offer,
        requirement=req,
        acp_job_id=record.acp_job_id,
        deliverable=record.deliverable,
    )


def _reusable_job(workspace_id: str, raw: str) -> JobRecord | None:
    needle = (raw or "").strip()
    if not needle:
        return None
    for record in jobs.list_for(workspace_id):
        if record.status not in _OPEN_JOB_STATUSES:
            continue
        if (record.spec.raw or "").strip() == needle:
            return record
    return None
