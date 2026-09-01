"""Compatibility shim. New code should import prior.providers."""

from prior.providers.base import ProviderError as AcpUnavailable
from prior.providers import active_provider
from prior.domain import JobSpec

__all__ = ["AcpUnavailable", "discover_or_fail"]


def discover_or_fail():
    spec = JobSpec(
        job_type="research",
        goal="research",
        subject="research",
        domain="research",
        count=None,
        deliverables=[],
        explicit_requirements=[],
        time_sensitive=False,
        raw="research",
    )
    return active_provider().find_providers(spec)
