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
from prior.providers.base import ProviderError, ProviderJob
from prior.providers.local import LOCAL_SOURCE


def new_ids() -> str:
    return "job_" + uuid.uuid4().hex[:12]


def specify(workspace_id: str, raw: str) -> JobRecord:
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
    record = _owned(workspace_id, job_id)
    if record.status == "refused":
        raise ValueError(record.error or "This job is outside the research domain.")
    if record.contract.memory_status == "unavailable":
        raise MemoryUnavailable(MEMORY_UNAVAILABLE)
    provider = active_provider()
    offers = provider.find_providers(record.spec)
    offer = offers[0]
    started = provider.create_job(offer, record.contract, record.spec)
    return _apply_provider_job(record, started)


def refresh(workspace_id: str, job_id: str) -> JobRecord:
    record = _owned(workspace_id, job_id)
    if record.status not in {"hired", "working"}:
        return record
    if not record.provider:
        return record
    provider = provider_for_record(record)
    current = _record_to_provider_job(record)
    updated = provider.get_job_status(current)
    return _apply_provider_job(record, updated)


def accept(workspace_id: str, job_id: str) -> JobRecord:
    record = _owned(workspace_id, job_id)
    if record.status != "delivered":
        raise ValueError("Only a delivered job can be accepted.")
    provider = provider_for_record(record)
    evaluated = provider.evaluate(
        _record_to_provider_job(record), True, "Accepted by the hiring user."
    )
    record.acp_phase = evaluated.phase
    if evaluated.extra.get("txHash"):
        record.tx_hash = str(evaluated.extra["txHash"])
    record.evaluation = "accepted"
    record.status = "accepted"
    record.updated_at = now_iso()
    return jobs.put(record)


def reject(workspace_id: str, job_id: str, reason: str) -> JobRecord:
    record = _owned(workspace_id, job_id)
    if record.status != "delivered":
        raise ValueError("Only a delivered job can be rejected.")
    if not (reason or "").strip():
        raise ValueError("A rejection needs a useful reason.")
    provider = provider_for_record(record)
    evaluated = provider.evaluate(_record_to_provider_job(record), False, reason.strip())
    record.acp_phase = evaluated.phase
    if evaluated.extra.get("txHash"):
        record.tx_hash = str(evaluated.extra["txHash"])
    record.evaluation = "rejected"
    record.rejection_reason = reason.strip()
    record.status = "rejected"
    record.proposed_lesson = propose_lesson(record, reason).to_dict()
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
    record.worker_requirement = started.requirement
    if started.extra.get("txHash"):
        record.tx_hash = str(started.extra["txHash"])
    if started.deliverable:
        record.deliverable = started.deliverable
        record.status = "delivered"
    elif started.source == LOCAL_SOURCE:
        record.status = "working"
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
    return ProviderJob(
        source=str(offer_data.get("source") or ""),
        phase=record.acp_phase or record.status,
        offer=offer,
        requirement=record.contract.to_dict(),
        acp_job_id=record.acp_job_id,
        deliverable=record.deliverable,
    )
