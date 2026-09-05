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
    writer_file = tmp_path / "writer.py"
    reader_file = tmp_path / "reader.py"
    writer_file.write_text(writer, encoding="utf-8")
    reader_file.write_text(reader, encoding="utf-8")
    subprocess.run([sys.executable, str(writer_file)], check=True, stdin=subprocess.DEVNULL, capture_output=True)
    res = subprocess.run([sys.executable, str(reader_file)], check=True, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    assert "source links" in res.stdout.strip().lower()


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


def test_rejection_does_not_persist_until_explicit_approval(tmp_path, monkeypatch):
    from prior import service
    from prior.providers.local import LocalResearchProvider

    db = tmp_path / "sibyl.db"
    monkeypatch.setattr(settings, "memory_db_path", lambda: db)
    monkeypatch.setattr(
        "prior.providers.local.run_research",
        lambda spec, contract: {"type": "object", "value": {"findings": [{"name": "A", "summary": "B"}]}},
    )
    monkeypatch.setattr(service, "active_provider", lambda: LocalResearchProvider())

    ws = "ws_approval_flow"
    job = service.specify(ws, "Research three password managers.")
    service.hire(ws, job.id)
    
    # User rejects work with specific feedback
    feedback = (
        "When reporting pricing, map every numeric price to the exact plan it belongs to "
        "and include the billing unit, such as per user per month or per year. "
        "Do not list unexplained prices."
    )
    rejected = service.reject(ws, job.id, feedback)
    
    # 1. Proposal is created with status "proposed"
    assert rejected.proposed_lesson is not None
    assert rejected.proposed_lesson["status"] == "proposed"
    assert rejected.proposed_lesson["requirement"] == feedback
    
    # 2. Sibyl memory is still EMPTY before explicit approval
    lessons_before = list_lessons(ws)
    assert len(lessons_before) == 0
    mem_view_before = service.memory_view(ws)
    assert mem_view_before["count"] == 0
    assert len([l for l in mem_view_before["lessons"] if l["status"] == "active"]) == 0
    
    # 3. Explicit user approval writes to Sibyl
    approved = service.decide_lesson(ws, job.id, "add")
    assert approved.proposed_lesson["status"] == "active"
    assert approved.proposed_lesson["provenance"] == "user-approved"
    
    # 4. Sibyl memory now has exactly 1 active lesson
    lessons_after = list_lessons(ws)
    assert len(lessons_after) == 1
    assert lessons_after[0].status == "active"
    assert lessons_after[0].requirement == feedback
    mem_view_after = service.memory_view(ws)
    assert mem_view_after["count"] == 1

