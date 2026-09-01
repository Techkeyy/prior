from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SUPPORTED_JOB_TYPE = "research"
UNSUPPORTED_JOB_TYPE = "unsupported"
LESSON_CATEGORY = "lesson"


@dataclass
class JobSpec:
    job_type: str
    goal: str
    subject: str
    domain: str
    count: int | None
    deliverables: list[str]
    explicit_requirements: list[str]
    time_sensitive: bool
    raw: str
    refusal_reason: str | None = None
    keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_type": self.job_type,
            "goal": self.goal,
            "subject": self.subject,
            "domain": self.domain,
            "count": self.count,
            "deliverables": list(self.deliverables),
            "explicit_requirements": list(self.explicit_requirements),
            "time_sensitive": self.time_sensitive,
            "raw": self.raw,
            "refusal_reason": self.refusal_reason,
            "keywords": list(self.keywords),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobSpec":
        return cls(
            job_type=str(data.get("job_type") or UNSUPPORTED_JOB_TYPE),
            goal=str(data.get("goal") or ""),
            subject=str(data.get("subject") or ""),
            domain=str(data.get("domain") or ""),
            count=data.get("count"),
            deliverables=list(data.get("deliverables") or []),
            explicit_requirements=list(data.get("explicit_requirements") or []),
            time_sensitive=bool(data.get("time_sensitive")),
            raw=str(data.get("raw") or ""),
            refusal_reason=data.get("refusal_reason"),
            keywords=list(data.get("keywords") or []),
        )


@dataclass
class Lesson:
    id: str
    workspace_id: str
    job_type: str
    issue: str
    requirement: str
    reason: str
    source_job_id: str | None = None
    originating_evaluation: str | None = None
    status: str = "active"
    provenance: str = "user-approved"
    created_at: str = ""
    domains: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    match_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "job_type": self.job_type,
            "issue": self.issue,
            "requirement": self.requirement,
            "reason": self.reason,
            "source_job_id": self.source_job_id,
            "originating_evaluation": self.originating_evaluation,
            "status": self.status,
            "provenance": self.provenance,
            "created_at": self.created_at,
            "domains": list(self.domains),
            "keywords": list(self.keywords),
            "match_reason": self.match_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], fallback_id: str = "") -> "Lesson":
        return cls(
            id=str(data.get("id") or fallback_id),
            workspace_id=str(data.get("workspace_id") or ""),
            job_type=str(data.get("job_type") or SUPPORTED_JOB_TYPE),
            issue=str(data.get("issue") or ""),
            requirement=str(data.get("requirement") or ""),
            reason=str(data.get("reason") or ""),
            source_job_id=data.get("source_job_id"),
            originating_evaluation=data.get("originating_evaluation"),
            status=str(data.get("status") or "active"),
            provenance=str(data.get("provenance") or "user-approved"),
            created_at=str(data.get("created_at") or ""),
            domains=list(data.get("domains") or []),
            keywords=list(data.get("keywords") or []),
            match_reason=data.get("match_reason"),
        )


@dataclass
class Contract:
    title: str
    goal: str
    deliverables: list[str]
    acceptance: list[str]
    applied_lessons: list[Lesson] = field(default_factory=list)
    baseline: bool = True
    memory_status: str = "ok"
    memory_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "goal": self.goal,
            "deliverables": list(self.deliverables),
            "acceptance": list(self.acceptance),
            "applied_lessons": [lesson.to_dict() for lesson in self.applied_lessons],
            "baseline": self.baseline,
            "memory_status": self.memory_status,
            "memory_message": self.memory_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Contract":
        return cls(
            title=str(data.get("title") or ""),
            goal=str(data.get("goal") or ""),
            deliverables=list(data.get("deliverables") or []),
            acceptance=list(data.get("acceptance") or []),
            applied_lessons=[
                Lesson.from_dict(item) for item in (data.get("applied_lessons") or [])
            ],
            baseline=bool(data.get("baseline", True)),
            memory_status=str(data.get("memory_status") or "ok"),
            memory_message=data.get("memory_message"),
        )


@dataclass
class AgentOffer:
    id: str
    name: str
    summary: str
    price_label: str
    source: str
    network: str
    wallet_address: str | None = None
    offering_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "summary": self.summary,
            "price_label": self.price_label,
            "source": self.source,
            "network": self.network,
            "wallet_address": self.wallet_address,
            "offering_name": self.offering_name,
        }


@dataclass
class JobRecord:
    id: str
    workspace_id: str
    spec: JobSpec
    contract: Contract
    status: str
    created_at: str
    updated_at: str
    provider: dict[str, Any] | None = None
    acp_job_id: str | None = None
    acp_phase: str | None = None
    deliverable: dict[str, Any] | None = None
    evaluation: str | None = None
    rejection_reason: str | None = None
    proposed_lesson: dict[str, Any] | None = None
    error: str | None = None
    worker_requirement: dict[str, Any] | None = None
    tx_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "spec": self.spec.to_dict(),
            "contract": self.contract.to_dict(),
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "provider": self.provider,
            "acp_job_id": self.acp_job_id,
            "acp_phase": self.acp_phase,
            "deliverable": self.deliverable,
            "evaluation": self.evaluation,
            "rejection_reason": self.rejection_reason,
            "proposed_lesson": self.proposed_lesson,
            "error": self.error,
            "worker_requirement": self.worker_requirement,
            "tx_hash": self.tx_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobRecord":
        return cls(
            id=str(data["id"]),
            workspace_id=str(data["workspace_id"]),
            spec=JobSpec.from_dict(data.get("spec") or {}),
            contract=Contract.from_dict(data.get("contract") or {}),
            status=str(data.get("status") or "specified"),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            provider=data.get("provider"),
            acp_job_id=data.get("acp_job_id"),
            acp_phase=data.get("acp_phase"),
            deliverable=data.get("deliverable"),
            evaluation=data.get("evaluation"),
            rejection_reason=data.get("rejection_reason"),
            proposed_lesson=data.get("proposed_lesson"),
            error=data.get("error"),
            worker_requirement=data.get("worker_requirement"),
            tx_hash=data.get("tx_hash"),
        )
