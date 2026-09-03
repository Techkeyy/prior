import json
import os
from pathlib import Path
import subprocess
import sys

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
    from prior.memory import disable_lesson, list_lessons as list_again
    disable_lesson("ws_alice", "L_alice")
    assert list_again("ws_alice")[0].status == "disabled"


def test_workspace_cookie_stability_across_processes():
    script = """
import json, os, sys
from fastapi.testclient import TestClient
from prior.app import app

client = TestClient(app)
workspace = sys.argv[1] if len(sys.argv) > 1 else None
if workspace:
    client.cookies.set("prior_workspace", workspace)
response = client.get("/api/workspace")
print(json.dumps({"pid": os.getpid(), "workspace_id": response.json()["workspace_id"]}))
"""
    env = os.environ.copy()
    root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = str(root / "src")
    process_a = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    workspace_id = json.loads(process_a.stdout)["workspace_id"]
    process_b = subprocess.run(
        [sys.executable, "-c", script, workspace_id],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    first = json.loads(process_a.stdout)
    second = json.loads(process_b.stdout)
    assert first["pid"] != second["pid"]
    assert workspace_id.startswith("ws_")
    assert second["workspace_id"] == workspace_id


def test_disabled_lessons_do_not_apply_after_restart(tmp_path, monkeypatch):
    from prior import service, settings
    from prior.memory import disable_lesson, list_lessons
    from prior.providers.local import LocalResearchProvider

    db = tmp_path / "sibyl.db"
    monkeypatch.setattr(settings, "memory_db_path", lambda: db)
    monkeypatch.setattr(service, "active_provider", lambda: LocalResearchProvider())

    ws = "ws_restart_test"
    j1 = service.specify(ws, "Research the top five AI wallet companies.")
    service.hire(ws, j1.id)
    service.reject(ws, j1.id, "Material factual claims must include identifiable source links.")
    service.decide_lesson(ws, j1.id, "add")

    lessons = list_lessons(ws)
    assert len(lessons) == 1
    assert lessons[0].status == "active"

    # Disable the lesson
    disable_lesson(ws, lessons[0].id)
    assert list_lessons(ws)[0].status == "disabled"

    # Simulate fresh job after server restart / new process
    j2 = service.specify(ws, "Research the top five decentralized exchanges.")
    # Contract should be baseline because the active lesson was disabled
    assert j2.contract.baseline is True
    assert len(j2.contract.applied_lessons) == 0
