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
    return {
        "goal": contract.goal,
        "title": contract.title,
        "deliverables": contract.deliverables,
        "acceptance": contract.acceptance,
        "applied_lessons": [lesson.to_dict() for lesson in contract.applied_lessons],
        "raw": spec.raw,
        "subject": spec.subject,
        "domain": spec.domain,
        "time_sensitive": spec.time_sensitive,
        "job_type": spec.job_type,
        "count": spec.count,
        "keywords": spec.keywords,
        "explicit_requirements": spec.explicit_requirements,
    }
