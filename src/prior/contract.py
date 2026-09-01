from __future__ import annotations

from prior.domain import Contract, JobSpec, Lesson, SUPPORTED_JOB_TYPE
from prior.memory import MEMORY_UNAVAILABLE


def baseline_acceptance(spec: JobSpec) -> list[str]:
    items = [
        "Cover the requested subject with the named deliverables.",
        "Separate facts from speculation.",
    ]
    if spec.time_sensitive:
        items.append("Prefer recent sources and state the retrieval date.")
    items.extend(spec.explicit_requirements)
    return _unique(items)


def build_contract(
    spec: JobSpec,
    lessons: list[Lesson] | None = None,
    *,
    memory_status: str = "ok",
    memory_message: str | None = None,
) -> Contract:
    if spec.job_type != SUPPORTED_JOB_TYPE:
        return Contract(
            title="Unsupported job",
            goal=spec.goal or spec.raw,
            deliverables=[],
            acceptance=[],
            applied_lessons=[],
            baseline=True,
            memory_status=memory_status,
            memory_message=spec.refusal_reason or memory_message,
        )

    acceptance = baseline_acceptance(spec)
    applied: list[Lesson] = []
    for lesson in lessons or []:
        if lesson.requirement and lesson.requirement not in acceptance:
            acceptance.append(lesson.requirement)
        applied.append(lesson)

    title = spec.goal or spec.raw
    return Contract(
        title=title,
        goal=spec.goal,
        deliverables=list(spec.deliverables),
        acceptance=acceptance,
        applied_lessons=applied,
        baseline=not applied,
        memory_status=memory_status,
        memory_message=memory_message,
    )


def unavailable_contract(spec: JobSpec) -> Contract:
    contract = build_contract(spec, [])
    contract.memory_status = "unavailable"
    contract.memory_message = MEMORY_UNAVAILABLE
    return contract


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out
