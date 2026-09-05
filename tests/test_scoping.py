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


def test_workspace_cookie_stability_across_processes(tmp_path):
    runner = tmp_path / "run_ws.py"
    runner.write_text(
        "import json, os, sys\n"
        "from fastapi.testclient import TestClient\n"
        "from prior.app import app\n"
        "workspace = sys.argv[1] if len(sys.argv) > 1 else None\n"
        "with TestClient(app) as client:\n"
        "    if workspace:\n"
        "        client.cookies.set('prior_workspace', workspace)\n"
        "    response = client.get('/api/workspace')\n"
        "    print(json.dumps({'pid': os.getpid(), 'workspace_id': response.json()['workspace_id']}), flush=True)\n"
    )
    env = os.environ.copy()
    root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = os.pathsep.join([str(root / "src")] + [p for p in sys.path if p])
    venv_python = Path(sys.prefix) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    py_bin = str(venv_python) if venv_python.exists() else sys.executable
    process_a = subprocess.run(
        [py_bin, str(runner)],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    workspace_id = json.loads(process_a.stdout)["workspace_id"]
    process_b = subprocess.run(
        [py_bin, str(runner), workspace_id],
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
    monkeypatch.setattr(
        "prior.providers.local.run_research",
        lambda spec, contract: {"type": "object", "value": {"findings": []}},
    )

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


def test_two_browsers_keep_isolated_memory(monkeypatch):
    """User A and user B are different cookies and never share lessons."""
    from fastapi.testclient import TestClient

    from prior import service
    from prior.app import app
    from prior.providers.local import LocalResearchProvider

    monkeypatch.setattr(service, "active_provider", lambda: LocalResearchProvider())
    monkeypatch.setattr(
        "prior.providers.local.run_research",
        lambda spec, contract: {"type": "object", "value": {"findings": []}},
    )

    browser_a = TestClient(app)
    ws_a = browser_a.get("/api/workspace").json()["workspace_id"]
    job_a = browser_a.post("/api/jobs", json={"text": "Research the top five AI wallet companies."}).json()
    browser_a.post(f"/api/jobs/{job_a['id']}/hire")
    browser_a.post(
        f"/api/jobs/{job_a['id']}/reject",
        json={"reason": "Material factual claims must include identifiable source links."},
    )
    decided = browser_a.post(f"/api/jobs/{job_a['id']}/lessons", json={"action": "add"}).json()
    assert decided["proposed_lesson"]["status"] == "active"

    browser_b = TestClient(app)
    ws_b = browser_b.get("/api/workspace").json()["workspace_id"]
    assert ws_b != ws_a
    job_b = browser_b.post(
        "/api/jobs",
        json={"text": "Research the top five AI wallet companies."},
    ).json()
    assert job_b["contract"]["baseline"] is True
    assert job_b["contract"]["applied_lessons"] == []
    assert browser_b.get("/api/memory").json()["lessons"] == []
    assert browser_b.get("/api/memory").json()["count"] == 0

    browser_a_again = TestClient(app)
    browser_a_again.cookies.set("prior_workspace", ws_a)
    assert browser_a_again.get("/api/workspace").json()["workspace_id"] == ws_a
    job_a2 = browser_a_again.post(
        "/api/jobs", json={"text": "Research the top five decentralized exchanges."}
    ).json()
    assert job_a2["contract"]["baseline"] is False
    assert len(job_a2["contract"]["applied_lessons"]) == 1
