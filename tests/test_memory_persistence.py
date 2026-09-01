import json
import subprocess
import sys
from pathlib import Path

from prior.contract import build_contract
from prior.domain import Lesson
from prior.job_spec import parse_job
from prior.lessons import applicable_lessons, is_duplicate, now_iso
from prior.memory import list_lessons, recall_lessons, write_lesson
from prior import settings


def test_approved_lesson_persistence(tmp_path, monkeypatch):
    db = tmp_path / "sibyl.db"
    monkeypatch.setattr(settings, "memory_db_path", lambda: db)
    lesson = Lesson(
        id="L_persist",
        workspace_id="ws_p",
        job_type="research",
        issue="sources",
        requirement="Material factual claims must include identifiable source links.",
        reason="approved",
        status="active",
        created_at=now_iso(),
        keywords=["research", "sources"],
        domains=["decentralized exchanges"],
    )
    write_lesson("ws_p", lesson)
    stored = list_lessons("ws_p")
    assert stored[0].requirement == lesson.requirement


def test_duplicate_lesson_handling(tmp_path, monkeypatch):
    db = tmp_path / "sibyl.db"
    monkeypatch.setattr(settings, "memory_db_path", lambda: db)
    lesson = Lesson(
        id="L_dup1",
        workspace_id="ws_p",
        job_type="research",
        issue="sources",
        requirement="Material factual claims must include identifiable source links.",
        reason="one",
        status="active",
        created_at=now_iso(),
    )
    write_lesson("ws_p", lesson)
    existing = list_lessons("ws_p")
    dup = is_duplicate(existing, "Material factual claims must include identifiable source links.")
    assert dup is not None
    assert is_duplicate(existing, "A completely different rule about suppliers.") is None


def test_fresh_process_sibyl_recall(tmp_path):
    db = tmp_path / "fresh.db"
    script = tmp_path / "fresh_read.py"
    writer = f"""
from sibyl_memory_client import MemoryClient
c = MemoryClient.local(r"{db}", tenant_id="ws_fresh")
c.set_entity("lesson", "L_fresh", {{
    "id": "L_fresh",
    "workspace_id": "ws_fresh",
    "job_type": "research",
    "status": "active",
    "requirement": "Material factual claims must include identifiable source links.",
    "issue": "Unsupported factual claims",
    "keywords": ["research", "sources"],
    "domains": ["decentralized exchanges"],
}})
print("wrote")
"""
    reader = f"""
from sibyl_memory_client import MemoryClient
c = MemoryClient.local(r"{db}", tenant_id="ws_fresh")
row = c.get_entity("lesson", "L_fresh")
print(row["body"]["requirement"])
"""
    subprocess.check_output([sys.executable, "-c", writer], text=True)
    out = subprocess.check_output([sys.executable, "-c", reader], text=True).strip()
    assert "source links" in out.lower()


def test_recalled_lesson_changes_contract(tmp_path, monkeypatch):
    db = tmp_path / "sibyl.db"
    monkeypatch.setattr(settings, "memory_db_path", lambda: db)
    write_lesson(
        "ws_p",
        Lesson(
            id="L_x",
            workspace_id="ws_p",
            job_type="research",
            issue="Unsupported factual claims",
            requirement="Material factual claims must include identifiable source links.",
            reason="job 1",
            status="active",
            created_at=now_iso(),
            domains=["decentralized exchanges"],
            keywords=["exchanges", "sources"],
        ),
    )
    spec = parse_job("Research the top five decentralized exchanges.")
    recalled = recall_lessons("ws_p", spec.raw, spec.keywords)
    applied = applicable_lessons(spec, recalled)
    contract = build_contract(spec, applied)
    assert any("source" in item.lower() for item in contract.acceptance)
    assert contract.baseline is False
