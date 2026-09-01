from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SUPPORTED_JOB_TYPE = "research"
UNSUPPORTED_JOB_TYPE = "unsupported"


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
    issue: str
    requirement: str
    job_type: str
    domains: list[str]
    keywords: list[str]
    source_job_id: str | None = None
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "issue": self.issue,
            "requirement": self.requirement,
            "job_type": self.job_type,
            "domains": list(self.domains),
            "keywords": list(self.keywords),
            "source_job_id": self.source_job_id,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], fallback_id: str = "") -> "Lesson":
        return cls(
            id=str(data.get("id") or fallback_id),
            issue=str(data.get("issue") or ""),
            requirement=str(data.get("requirement") or ""),
            job_type=str(data.get("job_type") or SUPPORTED_JOB_TYPE),
            domains=list(data.get("domains") or []),
            keywords=list(data.get("keywords") or []),
            source_job_id=data.get("source_job_id"),
            status=str(data.get("status") or "active"),
        )


@dataclass
class Contract:
    title: str
    goal: str
    deliverables: list[str]
    acceptance: list[str]
    applied_lessons: list[Lesson] = field(default_factory=list)
    baseline: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "goal": self.goal,
            "deliverables": list(self.deliverables),
            "acceptance": list(self.acceptance),
            "applied_lessons": [lesson.to_dict() for lesson in self.applied_lessons],
            "baseline": self.baseline,
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
        )


@dataclass
class AgentOffer:
    id: str
    name: str
    summary: str
    price_label: str
    source: str
    wallet_address: str | None = None
    offering_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "summary": self.summary,
            "price_label": self.price_label,
            "source": self.source,
            "wallet_address": self.wallet_address,
            "offering_name": self.offering_name,
        }
