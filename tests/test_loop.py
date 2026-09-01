from prior import acp, service
from prior.lessons import is_duplicate
from prior.memory import list_lessons, recall_lessons
from prior.job_spec import parse_job
from prior.lessons import applicable_lessons
from prior.contract import build_contract


def test_full_learning_loop_with_labelled_local_provider(monkeypatch):
    monkeypatch.setattr(acp, "acp_ready", lambda: False)
    monkeypatch.setattr(acp, "local_provider_enabled", lambda: True)

    def fake_research(spec, contract):
        return {
            "type": "object",
            "value": {
                "title": contract.title,
                "findings": [{"name": "Example Co", "summary": "No sources."}],
                "honored_requirements": list(contract.acceptance),
                "applied_lesson_ids": [lesson.id for lesson in contract.applied_lessons],
            },
        }

    monkeypatch.setattr(service, "run_research", fake_research)

    first = service.specify("ws_loop", "Research the top five AI wallet companies.")
    assert first.contract.baseline is True
    hired = service.hire("ws_loop", first.id)
    assert hired.status == "delivered"
    assert hired.provider["source"] == "local-development"
    assert hired.acp_job_id is None
    rejected = service.reject("ws_loop", first.id, "Important factual claims should include source links.")
    assert rejected.proposed_lesson
    stored = service.decide_lesson("ws_loop", first.id, "add")
    assert stored.proposed_lesson["status"] == "active"
    lessons = list_lessons("ws_loop")
    assert len(lessons) == 1

    second = service.specify("ws_loop", "Research the top five decentralized exchanges.")
    assert second.contract.baseline is False
    assert any("source" in item.lower() for item in second.contract.acceptance)
    assert second.contract.applied_lessons[0].id == lessons[0].id


def test_ignore_does_not_write_policy(monkeypatch):
    monkeypatch.setattr(acp, "acp_ready", lambda: False)
    monkeypatch.setattr(acp, "local_provider_enabled", lambda: True)
    monkeypatch.setattr(
        service,
        "run_research",
        lambda spec, contract: {"type": "object", "value": {"findings": []}},
    )
    first = service.specify("ws_ignore", "Research the top five AI wallet companies.")
    service.hire("ws_ignore", first.id)
    service.reject("ws_ignore", first.id, "Pricing was missing.")
    service.decide_lesson("ws_ignore", first.id, "ignore")
    assert list_lessons("ws_ignore") == []
