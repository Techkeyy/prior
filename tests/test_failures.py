from prior.acp import AcpUnavailable, discover_or_fail
from prior.memory import MemoryUnavailable, open_memory
from prior.service import hire, specify
from prior import jobs as jobs_mod
from prior.providers.base import ProviderError


def test_acp_failure_is_honest(monkeypatch):
    monkeypatch.setattr("prior.providers.acp_enabled", lambda: False)
    monkeypatch.setattr("prior.providers.local_provider_enabled", lambda: False)
    try:
        discover_or_fail()
        raise AssertionError("should have failed")
    except (AcpUnavailable, ProviderError) as exc:
        assert "not configured" in str(exc).lower()


def test_memory_open_requires_workspace():
    try:
        open_memory("")
        raise AssertionError("should have failed")
    except MemoryUnavailable:
        pass


def test_hire_without_provider_does_not_fake_success(monkeypatch):
    monkeypatch.setattr("prior.providers.acp_enabled", lambda: False)
    monkeypatch.setattr("prior.providers.local_provider_enabled", lambda: False)
    record = specify("ws_test", "Research the top five AI wallet companies.")
    try:
        hire("ws_test", record.id)
        raise AssertionError("hire should fail without a provider")
    except ProviderError:
        again = jobs_mod.get(record.id, "ws_test")
        assert again.status != "delivered"
        assert again.acp_job_id is None
