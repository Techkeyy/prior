"""Frontend reset + backend truth for the post-lesson 'Start a new job' UAT.

The node harness executes the REAL app.js bundle and proves every [data-reset]
control shares one live handler (regression for the singular-querySelector
binding bug). The integrated test below replays the owner's UAT sequence on
isolated stores — delivered -> reject -> lesson add -> active — and proves the
backend leaves the lesson, history, and workspace exactly where the UI expects
them while never touching ACP.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from prior import jobs as jobs_mod
from prior import service

HARNESS = Path(__file__).with_name("reset_button_check.cjs")
TEXT = "Research the top five AI wallet companies and compare their features."


def _run_node_harness(result_file: Path) -> subprocess.CompletedProcess:
    # stdio inherited: piped children hit the documented Windows handle flake.
    last = None
    for _ in range(3):
        try:
            return subprocess.run(
                ["node", str(HARNESS), str(result_file)], timeout=60
            )
        except OSError as exc:
            last = exc
    raise last


def test_real_bundle_resets_every_data_reset_control(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node unavailable")
    result_file = tmp_path / "frontend_reset_wiring.txt"
    proc = _run_node_harness(result_file)
    assert proc.returncode == 0
    assert result_file.read_text(encoding="utf-8").strip() == "FRONTEND_RESET_WIRING_OK"


def test_owner_uat_sequence_backend_truth(monkeypatch):
    import prior.providers.virtuals as vm

    def _boom(args):
        raise AssertionError(f"lesson flow must never reach the ACP bridge: {args}")

    monkeypatch.setattr(vm, "_bridge", _boom)
    monkeypatch.setattr(
        "prior.providers.local.run_research",
        lambda spec, contract: {"type": "object", "value": {"findings": []}},
    )
    from prior.providers.local import LocalResearchProvider
    monkeypatch.setattr(service, "active_provider", lambda: LocalResearchProvider())

    record = service.specify("ws_rbuat", TEXT)
    service.hire("ws_rbuat", record.id)
    rejected = service.reject("ws_rbuat", record.id,
                              "Claims lacked source links from the supplied fields.")
    assert rejected.status == "rejected"
    assert rejected.proposed_lesson["status"] == "proposed"

    saved = service.decide_lesson("ws_rbuat", record.id, "add")
    assert saved.proposed_lesson["status"] == "active"
    assert saved.status == "rejected"
    assert saved.rejection_reason == "Claims lacked source links from the supplied fields."

    # Active lesson present; historical job intact in the same workspace;
    # nothing else created. 'Start a new job' is a pure client reset: no
    # backend call is (or can be) required for it.
    from prior.memory import list_lessons
    lessons = list_lessons("ws_rbuat")
    assert len(lessons) == 1 and lessons[0].status == "active"
    workspace_jobs = jobs_mod.list_for("ws_rbuat")
    assert [j.id for j in workspace_jobs] == [record.id]
    assert workspace_jobs[0].status == "rejected"
    assert jobs_mod.get(record.id, "ws_other_workspace") is None

    # A fresh request then behaves normally and recalls the lesson.
    second = service.specify("ws_rbuat", "Research the top five decentralized exchanges.")
    assert second.contract.baseline is False
    assert lessons[0].requirement in second.contract.acceptance


def test_accepted_and_ignored_views_keep_same_reset_control():
    source = Path("src/prior/static/app.js").read_text(encoding="utf-8")
    assert 'data-reset>Start a new job</button>' in source   # accepted + learning views
    assert 'data-reset>Start over' in source                 # request line
    assert 'data-reset>Discard' in source                    # specified view
    assert "querySelectorAll(\"[data-reset]\")" in source
