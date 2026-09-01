from pathlib import Path

from prior.domain import Lesson
from prior.lessons import now_iso
from prior.memory import list_lessons, tenant_cannot_see, write_lesson
from prior import settings


def test_user_scoping(tmp_path, monkeypatch):
    db = tmp_path / "sibyl.db"
    monkeypatch.setattr(settings, "memory_db_path", lambda: db)
    a = Lesson(
        id="L_alice",
        workspace_id="ws_alice",
        job_type="research",
        issue="sources",
        requirement="Material factual claims must include identifiable source links.",
        reason="alice",
        status="active",
        created_at=now_iso(),
    )
    b = Lesson(
        id="L_bob",
        workspace_id="ws_bob",
        job_type="research",
        issue="bob only",
        requirement="Bob-only rule.",
        reason="bob",
        status="active",
        created_at=now_iso(),
    )
    write_lesson("ws_alice", a)
    write_lesson("ws_bob", b)
    alice = list_lessons("ws_alice")
    bob = list_lessons("ws_bob")
    assert [item.id for item in alice] == ["L_alice"]
    assert [item.id for item in bob] == ["L_bob"]
    assert tenant_cannot_see("ws_alice", "L_bob") is True
    assert tenant_cannot_see("ws_bob", "L_alice") is True
