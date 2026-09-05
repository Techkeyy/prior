from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from prior.domain import JobRecord, JobSpec, Lesson, SUPPORTED_JOB_TYPE


def new_lesson_id() -> str:
    return "L_" + uuid.uuid4().hex[:16]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def applicable_lessons(spec: JobSpec, candidates: list[Lesson]) -> list[Lesson]:
    """Deterministic applicability. Never invents a lesson that was not retrieved."""
    if spec.job_type != SUPPORTED_JOB_TYPE:
        return []
    matched: list[Lesson] = []
    spec_tokens = set(_tokens(spec.raw + " " + spec.domain + " " + " ".join(spec.keywords)))
    for lesson in candidates:
        if lesson.status != "active":
            continue
        if lesson.job_type and lesson.job_type != spec.job_type:
            continue
        reason = _match_reason(spec, spec_tokens, lesson)
        if not reason:
            continue
        clone = Lesson.from_dict(lesson.to_dict())
        clone.match_reason = reason
        matched.append(clone)
    return matched


def propose_lesson(job: JobRecord, rejection_reason: str) -> Lesson:
    reason = (rejection_reason or "").strip()
    if not reason:
        raise ValueError("A rejection needs a useful reason before PRIOR can propose a lesson.")
    requirement = _requirement_from_reason(reason)
    issue = _issue_from_reason(reason)
    spec = job.spec
    return Lesson(
        id=new_lesson_id(),
        workspace_id=job.workspace_id,
        job_type=spec.job_type or SUPPORTED_JOB_TYPE,
        issue=issue,
        requirement=requirement,
        reason=f"Learned from rejected job {job.id}: {reason}",
        source_job_id=job.id,
        originating_evaluation="rejected",
        status="proposed",
        provenance="prior-proposed",
        created_at=now_iso(),
        domains=[spec.domain] if spec.domain else [],
        keywords=list(spec.keywords),
    )


def is_duplicate(existing: list[Lesson], requirement: str) -> Lesson | None:
    target = _norm(requirement)
    for lesson in existing:
        if lesson.status != "active":
            continue
        if _norm(lesson.requirement) == target:
            return lesson
    return None


def sanitize_payload(data: dict) -> dict:
    """Reject malicious or oversized lesson payloads. Keep only known fields."""
    allowed = {
        "id",
        "workspace_id",
        "job_type",
        "issue",
        "requirement",
        "reason",
        "source_job_id",
        "originating_evaluation",
        "status",
        "provenance",
        "created_at",
        "domains",
        "keywords",
    }
    display_only = {"match_reason", "existing_id"}
    unknown = set(data) - allowed - display_only
    if unknown:
        raise ValueError(f"Unexpected lesson fields: {sorted(unknown)}")
    requirement = str(data.get("requirement") or "").strip()
    if not requirement:
        raise ValueError("Lesson requirement cannot be empty.")
    if len(requirement) > 2000:
        raise ValueError("Lesson requirement is too long.")
    lesson_id = str(data.get("id") or "")
    if lesson_id and (".." in lesson_id or any(ch in lesson_id for ch in '<>|;"`')):
        raise ValueError("Invalid lesson id.")
    return {key: data[key] for key in data if key in allowed}


def _match_reason(spec: JobSpec, spec_tokens: set[str], lesson: Lesson) -> str | None:
    if lesson.job_type == spec.job_type and not lesson.domains and not lesson.keywords:
        return "Same job class (research)."
    for domain in lesson.domains:
        if domain and (domain.lower() in spec.domain.lower() or domain.lower() in spec.raw.lower()):
            return f"Domain overlap: {domain}."
    lesson_tokens = set(_tokens(" ".join(lesson.keywords + lesson.domains + [lesson.requirement, lesson.issue])))
    overlap = spec_tokens & lesson_tokens
    if len(overlap) >= 2:
        shown = ", ".join(sorted(overlap)[:4])
        return f"Shared terms: {shown}."
    if lesson.job_type == spec.job_type:
        return "Research job lesson."
    return None


def _requirement_from_reason(reason: str) -> str:
    text = (reason or "").strip()
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()
    if not text:
        return "Research jobs must satisfy all verified contract requirements."
    if text[0].islower():
        text = text[0].upper() + text[1:]
    if not text.endswith((".", "!", "?")):
        text += "."
    return text


def _issue_from_reason(reason: str) -> str:
    text = (reason or "").strip()
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()
    if not text:
        return "Unspecified issue"
    if len(text) > 80:
        text = text[:77] + "..."
    return text[0].upper() + text[1:]


def _tokens(text: str) -> list[str]:
    stop = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "must",
        "include",
        "research",
        "jobs",
        "job",
        "top",
        "five",
    }
    return [tok for tok in re.findall(r"[a-z0-9]{3,}", text.lower()) if tok not in stop]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())
