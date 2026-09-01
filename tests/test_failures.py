from prior.acp import AcpUnavailable, discover_or_fail
from prior import settings
from prior.memory import MemoryUnavailable, open_memory
from prior.service import hire, specify
from prior import settings as settings_mod


def test_acp_failure_is_honest(monkeypatch):
    monkeypatch.setattr(settings, "acp_ready", lambda: False)
    monkeypatch.setattr(settings, "local_provider_enabled", lambda: False)
    monkeypatch.setattr("prior.acp.acp_ready", lambda: False)
    monkeypatch.setattr("prior.acp.local_provider_enabled", lambda: False)
    try:
        discover_or_fail()
        raise AssertionError("should have failed")
    except AcpUnavailable as exc:
        assert "invent" in str(exc).lower() or "not configured" in str(exc).lower()


def test_memory_open_requires_workspace():
    try:
        open_memory("")
        raise AssertionError("should have failed")
    except MemoryUnavailable:
        pass


def test_hire_without_provider_does_not_fake_success(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "memory_db_path", lambda: tmp_path / "m.db")
    monkeypatch.setattr(settings_mod, "jobs_path", lambda: tmp_path / "jobs.json")
    monkeypatch.setattr(settings_mod, "acp_ready", lambda: False)
    monkeypatch.setattr(settings_mod, "local_provider_enabled", lambda: False)
    from prior import acp, jobs as jobs_mod
    monkeypatch.setattr(acp, "acp_ready", lambda: False)
    monkeypatch.setattr(acp, "local_provider_enabled", lambda: False)
    monkeypatch.setattr(jobs_mod, "jobs_path", lambda: tmp_path / "jobs.json")
    from prior import memory as memory_mod
    monkeypatch.setattr(memory_mod, "memory_db_path", lambda: tmp_path / "m.db")
    record = specify("ws_test", "Research the top five AI wallet companies.")
    try:
        hire("ws_test", record.id)
        raise AssertionError("hire should fail without a provider")
    except AcpUnavailable:
        again = jobs_mod.get(record.id, "ws_test")
        assert again.status != "delivered"
        assert again.acp_job_id is None
