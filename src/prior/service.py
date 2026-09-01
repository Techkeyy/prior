"""Core PRIOR loop: normalize, recall, contract, hire, evaluate, persist lessons."""

from __future__ import annotations

import uuid
from typing import Any

from prior import jobs
from prior.acp import AcpUnavailable, discover_or_fail, evaluate_job, initiate_job
from prior.contract import build_contract, unavailable_contract
from prior.domain import JobRecord, JobSpec, Lesson, SUPPORTED_JOB_TYPE
from prior.job_spec import parse_job
from prior.lessons import applicable_lessons, is_duplicate, now_iso, propose_lesson, sanitize_payload
from prior.memory import (
    MEMORY_UNAVAILABLE,
    MemoryUnavailable,
    list_lessons,
    open_memory,
    recall_lessons,
    write_lesson,
)
from prior.research import run_research


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
    offers = discover_or_fail()
    offer = offers[0]
    started = initiate_job(offer, record.contract, record.spec.to_dict())
    record.provider = started["provider"]
    record.acp_job_id = started.get("acp_job_id")
    record.acp_phase = started.get("phase")
    record.status = "working"
    record.updated_at = now_iso()
    jobs.put(record)

    if started["source"] == "local-development":
        deliverable = run_research(record.spec, record.contract)
        record.deliverable = deliverable
        record.acp_phase = "local.delivered"
        record.status = "delivered"
        record.updated_at = now_iso()
        return jobs.put(record)

    record.status = "hired"
    record.updated_at = now_iso()
    return jobs.put(record)


def accept(workspace_id: str, job_id: str) -> JobRecord:
    record = _owned(workspace_id, job_id)
    if record.status != "delivered":
        raise ValueError("Only a delivered job can be accepted.")
    source = (record.provider or {}).get("source") or "unknown"
    evaluate_job(record.acp_job_id, source, True, "Accepted by the hiring user.")
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
    source = (record.provider or {}).get("source") or "unknown"
    evaluate_job(record.acp_job_id, source, False, reason.strip())
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
        return {"status": "unavailable", "message": str(exc), "lessons": []}
    return {
        "status": "ok",
        "lessons": [lesson.to_dict() for lesson in lessons],
        "count": len(lessons),
    }


def _owned(workspace_id: str, job_id: str) -> JobRecord:
    record = jobs.get(job_id, workspace_id)
    if record is None:
        raise KeyError("Job not found in this workspace.")
    return record
