from prior import service
from prior.memory import list_lessons
from prior.providers.local import LOCAL_SOURCE, LocalResearchProvider


def test_full_learning_loop_with_labelled_local_provider(monkeypatch):
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

    monkeypatch.setattr("prior.providers.local.run_research", fake_research)
    monkeypatch.setattr(service, "active_provider", lambda: LocalResearchProvider())

    first = service.specify("ws_loop", "Research the top five AI wallet companies.")
    assert first.contract.baseline is True
    hired = service.hire("ws_loop", first.id)
    assert hired.status == "delivered"
    assert hired.provider["source"] == LOCAL_SOURCE
    assert hired.provider["name"] == "PRIOR Local Research Agent"
    assert hired.provider["network"] == "Local"
    assert hired.worker_requirement["learned_requirements"] == []
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
    hired2 = service.hire("ws_loop", second.id)
    assert lessons[0].requirement in hired2.worker_requirement["learned_requirements"]
    assert lessons[0].requirement in hired2.worker_requirement["acceptance"]


def test_ignore_does_not_write_policy(monkeypatch):
    monkeypatch.setattr(
        "prior.providers.local.run_research",
        lambda spec, contract: {"type": "object", "value": {"findings": []}},
    )
    monkeypatch.setattr(service, "active_provider", lambda: LocalResearchProvider())
    first = service.specify("ws_ignore", "Research the top five AI wallet companies.")
    service.hire("ws_ignore", first.id)
    service.reject("ws_ignore", first.id, "Pricing was missing.")
    service.decide_lesson("ws_ignore", first.id, "ignore")
    assert list_lessons("ws_ignore") == []
