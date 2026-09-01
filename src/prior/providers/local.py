"""LOCAL PROVIDER / DEVELOPMENT PROVIDER. Never Virtuals."""

from __future__ import annotations

from typing import Any

from prior.domain import AgentOffer, Contract, JobSpec
from prior.providers.base import ProviderError, ProviderJob, requirement_payload
from prior.research import run_research

LOCAL_SOURCE = "local-development"
LOCAL_NAME = "LOCAL PROVIDER"
LOCAL_SUMMARY = "Development provider. Runs research on this machine. Not Virtuals."


class LocalResearchProvider:
    kind = "local"

    def find_providers(self, spec: JobSpec) -> list[AgentOffer]:
        return [
            AgentOffer(
                id="local-research-provider",
                name=LOCAL_NAME,
                summary=LOCAL_SUMMARY,
                price_label="no onchain payment",
                source=LOCAL_SOURCE,
            )
        ]

    def create_job(self, offer: AgentOffer, contract: Contract, spec: JobSpec) -> ProviderJob:
        if offer.source != LOCAL_SOURCE:
            raise ProviderError("LOCAL PROVIDER cannot execute a non-local offer.")
        requirement = requirement_payload(contract, spec)
        deliverable = run_research(spec, contract)
        return ProviderJob(
            source=LOCAL_SOURCE,
            phase="local.delivered",
            offer=offer,
            requirement=requirement,
            acp_job_id=None,
            deliverable=deliverable,
        )

    def get_job_status(self, job: ProviderJob) -> ProviderJob:
        if job.deliverable:
            job.phase = "local.delivered"
        return job

    def get_deliverable(self, job: ProviderJob) -> dict[str, Any] | None:
        return job.deliverable

    def evaluate(self, job: ProviderJob, accepted: bool, reason: str) -> ProviderJob:
        job.phase = "local.accepted" if accepted else "local.rejected"
        job.extra["evaluation_reason"] = reason
        job.extra["onchain"] = False
        return job
