from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from prior.domain import AgentOffer, Contract, JobSpec


class ProviderError(RuntimeError):
    pass


VIRTUALS_NOT_CONFIGURED = "Virtuals credentials are not configured."


@dataclass
class ProviderJob:
    source: str
    phase: str
    offer: AgentOffer
    requirement: dict[str, Any]
    acp_job_id: str | None = None
    deliverable: dict[str, Any] | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "phase": self.phase,
            "offer": self.offer.to_dict(),
            "requirement": self.requirement,
            "acp_job_id": self.acp_job_id,
            "deliverable": self.deliverable,
            "error": self.error,
            "extra": self.extra,
        }


class ResearchProvider(Protocol):
    kind: str

    def find_providers(self, spec: JobSpec) -> list[AgentOffer]: ...

    def create_job(self, offer: AgentOffer, contract: Contract, spec: JobSpec) -> ProviderJob: ...

    def get_job_status(self, job: ProviderJob) -> ProviderJob: ...

    def get_deliverable(self, job: ProviderJob) -> dict[str, Any] | None: ...

    def evaluate(self, job: ProviderJob, accepted: bool, reason: str) -> ProviderJob: ...


def requirement_payload(contract: Contract, spec: JobSpec) -> dict[str, Any]:
    payload = {
        "goal": contract.goal,
        "title": contract.title,
        "deliverables": contract.deliverables,
        "acceptance": contract.acceptance,
        "applied_lessons": [lesson.to_dict() for lesson in contract.applied_lessons],
        "learned_requirements": [lesson.requirement for lesson in contract.applied_lessons],
        "raw": spec.raw,
        "subject": spec.subject,
        "domain": spec.domain,
        "time_sensitive": spec.time_sensitive,
        "job_type": spec.job_type,
        "count": spec.count,
        "keywords": spec.keywords,
        "explicit_requirements": spec.explicit_requirements,
    }
    payload["job_description"] = acp_job_description(payload)
    return payload


def acp_job_description(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    goal = str(payload.get("goal") or payload.get("raw") or "").strip()
    if goal:
        parts.append(goal)
    learned = [str(item).strip() for item in (payload.get("learned_requirements") or []) if str(item).strip()]
    if learned:
        parts.append("Learned requirements:")
        parts.extend(f"- {item}" for item in learned)
    acceptance = [str(item).strip() for item in (payload.get("acceptance") or []) if str(item).strip()]
    if acceptance:
        parts.append("Acceptance criteria:")
        parts.extend(f"- {item}" for item in acceptance)
    return "\n".join(parts)


def transmitted_learned_requirements(requirement: dict[str, Any] | None) -> list[str]:
    if not isinstance(requirement, dict):
        return []
    learned = requirement.get("learned_requirements")
    if not isinstance(learned, list):
        return []
    return [str(item) for item in learned if str(item).strip()]
