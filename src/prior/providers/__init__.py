from __future__ import annotations

from prior.domain import JobRecord
from prior.providers.base import (
    VIRTUALS_NOT_CONFIGURED,
    ProviderError,
    ProviderJob,
    ResearchProvider,
)
from prior.providers.local import LOCAL_SOURCE, LocalResearchProvider
from prior.providers.virtuals import VIRTUALS_SOURCE, VirtualsAcpProvider
from prior.settings import acp_enabled, local_provider_enabled


def active_provider() -> ResearchProvider:
    """Pick one provider. Never silently swap ACP failure for a local success."""
    if acp_enabled():
        return VirtualsAcpProvider()
    if local_provider_enabled():
        return LocalResearchProvider()
    raise ProviderError(VIRTUALS_NOT_CONFIGURED)


def provider_for_record(record: JobRecord) -> ResearchProvider:
    source = (record.provider or {}).get("source")
    if source == VIRTUALS_SOURCE:
        return VirtualsAcpProvider()
    if source == LOCAL_SOURCE:
        return LocalResearchProvider()
    return active_provider()


__all__ = [
    "LOCAL_SOURCE",
    "VIRTUALS_SOURCE",
    "ProviderError",
    "ProviderJob",
    "ResearchProvider",
    "LocalResearchProvider",
    "VirtualsAcpProvider",
    "active_provider",
    "provider_for_record",
]
