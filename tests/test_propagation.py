"""
Regression tests for learned-clause propagation from Sibyl recall through
contract build → provider-independent payload → worker execution input.
"""

from __future__ import annotations

import json

from prior import jobs, service
from prior.contract import build_contract
from prior.domain import AgentOffer, Lesson
from prior.job_spec import parse_job
from prior.lessons import now_iso
from prior.providers.base import acp_job_description, requirement_payload, transmitted_learned_requirements
from prior.providers.local import LocalResearchProvider
from prior.research import _comparative_summary, _learned_asks_comparison
from prior.research_cli import main as research_cli_main, spec_from_requirement


def _lesson(
    workspace: str = "ws_test",
    requirement: str = "Include a side-by-side comparison table.",
    status: str = "active",
) -> Lesson:
    return Lesson(
        id="L_test001",
        workspace_id=workspace,
        job_type="research",
        issue="No comparison was included.",
        requirement=requirement,
        reason="Learned from rejection.",
        status=status,
        provenance="user-approved",
        created_at=now_iso(),
        domains=["example products"],
        keywords=["compare", "pricing"],
    )


def _fake_research(spec, contract):
    return {
        "type": "object",
        "value": {
            "title": contract.title,
            "findings": [{"name": "Product A", "summary": "Test."}],
            "honored_requirements": list(contract.acceptance),
            "applied_lesson_ids": [item.id for item in contract.applied_lessons],
            "comparative_summary": _comparative_summary([{"name": "Product A", "pricing": "n/a"}])
            if _learned_asks_comparison(contract)
            else None,
        },
    }


def test_recalled_lesson_enters_contract():
    lesson = _lesson()
    spec = parse_job("Research three example products and compare their pricing and platforms.")
    contract = build_contract(spec, [lesson])
    assert len(contract.applied_lessons) == 1
    assert contract.applied_lessons[0].requirement == lesson.requirement
    assert lesson.requirement in contract.acceptance


def test_lesson_enters_requirement_payload():
    lesson = _lesson(requirement="Show a comparison section.")
    spec = parse_job("Compare three example products.")
    contract = build_contract(spec, [lesson])
    payload = requirement_payload(contract, spec)
    assert lesson.requirement in payload["learned_requirements"]
    assert lesson.requirement in payload["acceptance"]
    assert lesson.requirement in payload["job_description"]


def test_acp_request_contains_learned_requirement(monkeypatch):
    from prior.providers.virtuals import VirtualsAcpProvider

    lesson = _lesson(requirement="Include comparative summary.")
    spec = parse_job("Research example products.")
    contract = build_contract(spec, [lesson])
    captured = {}

    def fake_bridge(args):
        assert args[0] == "create-job"
        captured["payload"] = json.loads(args[3])
        return {"jobId": "999"}

    monkeypatch.setattr("prior.providers.virtuals.acp_ready", lambda: True)
    monkeypatch.setattr("prior.providers.virtuals._bridge", fake_bridge)
    offer = AgentOffer(
        id="0xSeller",
        name="Seller",
        summary="",
        price_label="",
        source="virtuals-acp",
        network="Virtuals ACP",
        wallet_address="0xSeller",
        offering_name="research",
    )
    VirtualsAcpProvider().create_job(offer, contract, spec)
    assert lesson.requirement in captured["payload"]["learned_requirements"]
    assert lesson.requirement in captured["payload"]["job_description"]
    assert lesson.requirement in acp_job_description(captured["payload"])


def test_research_cli_receives_learned_requirement(monkeypatch):
    lesson = _lesson(requirement="Include a side-by-side comparison.")
    spec = parse_job("Compare three example products.")
    contract = build_contract(spec, [lesson])
    payload = requirement_payload(contract, spec)
    received_contracts = []

    def fake_research(s, c):
        received_contracts.append(c)
        return {"type": "object", "value": {"findings": []}}

    monkeypatch.setattr("prior.research_cli.run_research", fake_research)
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(payload)))
    research_cli_main()
    received = received_contracts[0]
    assert lesson.requirement in received.acceptance
    assert any(item.requirement == lesson.requirement for item in received.applied_lessons)


def test_worker_contract_acceptance_contains_learned_requirement():
    lesson = _lesson(requirement="Do not only give separate profiles; include side-by-side comparison.")
    spec = parse_job("Compare three example products.")
    contract = build_contract(spec, [lesson])
    payload = requirement_payload(contract, spec)
    rebuilt_spec = spec_from_requirement(payload)
    rebuilt_lessons = [Lesson.from_dict(item) for item in (payload.get("applied_lessons") or [])]
    rebuilt_contract = build_contract(rebuilt_spec, rebuilt_lessons)
    if payload.get("acceptance"):
        rebuilt_contract.acceptance = list(payload["acceptance"])
    assert lesson.requirement in rebuilt_contract.acceptance
    assert _learned_asks_comparison(rebuilt_contract) is True
    summary = _comparative_summary(
        [
            {"name": "Alpha", "pricing": "$1", "strengths": "fast", "weaknesses": "cost"},
            {"name": "Beta", "pricing": "$2", "strengths": "simple", "weaknesses": "limits"},
        ]
    )
    assert "Side-by-side comparison" in summary
    assert "Alpha vs Beta" in summary
    assert "Pricing" in summary


def test_worker_requirement_not_overwritten_on_refresh(monkeypatch):
    from prior.providers.virtuals import VirtualsAcpProvider

    lesson = _lesson(requirement="Synthesize a comparison table.")
    monkeypatch.setattr("prior.service.applicable_lessons", lambda spec, candidates: [lesson])
    monkeypatch.setattr("prior.service.recall_lessons", lambda workspace_id, raw, tags: [])
    monkeypatch.setattr("prior.service.open_memory", lambda workspace_id: None)
    offer = AgentOffer(
        id="0xSeller",
        name="Seller",
        summary="",
        price_label="",
        source="virtuals-acp",
        network="Virtuals ACP",
        wallet_address="0xSeller",
        offering_name="research",
    )

    def fake_create_job(self_unused, offer, contract, spec):
        req = requirement_payload(contract, spec)
        from prior.providers.base import ProviderJob

        return ProviderJob(
            source="virtuals-acp",
            phase="job.created",
            offer=offer,
            requirement=req,
            acp_job_id="TEST_JOB_99",
        )

    monkeypatch.setattr(VirtualsAcpProvider, "find_providers", lambda self, spec: [offer])
    monkeypatch.setattr(VirtualsAcpProvider, "create_job", fake_create_job)
    monkeypatch.setattr(VirtualsAcpProvider, "get_job_status", lambda self, job: job)
    monkeypatch.setattr(service, "active_provider", lambda: VirtualsAcpProvider())
    record = service.specify("ws_refresh_virt", "Compare three example products.")
    hired = service.hire("ws_refresh_virt", record.id)
    assert lesson.requirement in hired.worker_requirement.get("learned_requirements", [])
    initial_learned = hired.worker_requirement.get("learned_requirements")
    refreshed = service.refresh("ws_refresh_virt", hired.id)
    assert refreshed.worker_requirement.get("learned_requirements") == initial_learned
    assert transmitted_learned_requirements(refreshed.to_dict()["worker_requirement"]) == [lesson.requirement]


def test_ui_sent_to_worker_uses_transmitted_not_contract():
    lesson = _lesson(requirement="Include a comparative summary.")
    spec = parse_job("Compare three example products.")
    contract = build_contract(spec, [lesson])
    stale = contract.to_dict()
    assert transmitted_learned_requirements(stale) == []
    payload = requirement_payload(contract, spec)
    assert transmitted_learned_requirements(payload) == [lesson.requirement]


def test_no_lessons_means_empty_learned_requirements():
    spec = parse_job("Research example products.")
    contract = build_contract(spec, [])
    payload = requirement_payload(contract, spec)
    assert payload["learned_requirements"] == []
    assert transmitted_learned_requirements(payload) == []
    assert "Learned requirements:" not in payload["job_description"]


def test_multiple_learned_clauses_survive_serialization():
    lesson_a = Lesson(
        id="L_a",
        workspace_id="ws_multi",
        job_type="research",
        issue="Missing comparison.",
        requirement="Include a comparison table.",
        reason="",
        status="active",
        provenance="user-approved",
        created_at=now_iso(),
    )
    lesson_b = Lesson(
        id="L_b",
        workspace_id="ws_multi",
        job_type="research",
        issue="Missing citations.",
        requirement="Every claim must cite a source.",
        reason="",
        status="active",
        provenance="user-approved",
        created_at=now_iso(),
    )
    spec = parse_job("Compare three example products.")
    contract = build_contract(spec, [lesson_a, lesson_b])
    recovered = json.loads(json.dumps(requirement_payload(contract, spec)))
    assert lesson_a.requirement in recovered["learned_requirements"]
    assert lesson_b.requirement in recovered["learned_requirements"]
    assert lesson_a.requirement in recovered["job_description"]
    assert lesson_b.requirement in recovered["job_description"]
    assert len(recovered["applied_lessons"]) == 2


def test_provider_switch_does_not_drop_learned_requirements():
    lesson = _lesson(requirement="Include a side-by-side comparison.")
    spec = parse_job("Research three example products.")
    contract = build_contract(spec, [lesson])
    recovered = json.loads(json.dumps(requirement_payload(contract, spec)))
    assert recovered["learned_requirements"] == [lesson.requirement]
    assert len(recovered["applied_lessons"]) == 1


def test_one_workflow_creates_one_job(monkeypatch):
    monkeypatch.setattr("prior.providers.local.run_research", _fake_research)
    monkeypatch.setattr(service, "active_provider", lambda: LocalResearchProvider())
    record = service.specify("ws_dedup", "Research three example products.")
    again = service.specify("ws_dedup", "Research three example products.")
    assert again.id == record.id
    hired = service.hire("ws_dedup", record.id)
    assert hired.id == record.id
    refreshed = service.refresh("ws_dedup", record.id)
    assert refreshed.id == record.id
    assert len(jobs.list_for("ws_dedup")) == 1


def test_job_stable_id_through_lifecycle(monkeypatch):
    monkeypatch.setattr("prior.providers.local.run_research", _fake_research)
    monkeypatch.setattr(service, "active_provider", lambda: LocalResearchProvider())
    specified = service.specify("ws_stable", "Research three example products.")
    assert specified.status == "specified"
    job_id = specified.id
    delivered = service.hire("ws_stable", job_id)
    assert delivered.id == job_id
    assert delivered.status == "delivered"
    accepted = service.accept("ws_stable", job_id)
    assert accepted.id == job_id
    assert accepted.status == "accepted"
    assert len(jobs.list_for("ws_stable")) == 1


def test_pending_lesson_not_in_execution_payload():
    pending = _lesson(requirement="Include citations.", status="proposed")
    active_lessons = [item for item in [pending] if item.status == "active"]
    spec = parse_job("Research three example products.")
    contract = build_contract(spec, active_lessons)
    payload = requirement_payload(contract, spec)
    assert payload["learned_requirements"] == []
    assert payload["applied_lessons"] == []
    assert pending.requirement not in payload["job_description"]
