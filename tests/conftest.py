from pathlib import Path
import uuid

import pytest

from prior import jobs, memory, settings


@pytest.fixture
def tmp_path():
    root = Path(__file__).resolve().parents[1] / ".pytest-tmp" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    monkeypatch.setenv("PRIOR_LOCAL_PROVIDER", "false")
    monkeypatch.setenv("ACP_ENABLED", "false")


@pytest.fixture(autouse=True)
def isolate_stores(tmp_path, monkeypatch):
    db = tmp_path / "sibyl-memory.db"
    jobfile = tmp_path / "jobs.json"
    identity_db = tmp_path / "identity.db"
    monkeypatch.setattr(settings, "memory_db_path", lambda: db)
    monkeypatch.setattr(settings, "jobs_path", lambda: jobfile)
    monkeypatch.setattr(settings, "identity_db_path", lambda: identity_db)
    monkeypatch.setattr(memory, "memory_db_path", lambda: db)
    monkeypatch.setattr(jobs, "jobs_path", lambda: jobfile)
