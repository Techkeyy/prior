from prior.contract import build_contract
from prior.domain import JobSpec, Lesson, SUPPORTED_JOB_TYPE
from prior.job_spec import parse_job


def test_contract_without_memory_is_baseline():
    spec = parse_job("Research the top five AI wallet companies.")
    contract = build_contract(spec, [])
    assert contract.baseline is True
    assert contract.applied_lessons == []
    assert any("deliverables" in item.lower() or "subject" in item.lower() for item in contract.acceptance)


def test_contract_with_memory_adds_requirement():
    spec = parse_job("Research the top five decentralized exchanges.")
    lesson = Lesson(
        id="L_1",
        workspace_id="ws_a",
        job_type=SUPPORTED_JOB_TYPE,
        issue="Unsupported factual claims",
        requirement="Material factual claims must include identifiable source links.",
        reason="from job 1",
        status="active",
    )
    contract = build_contract(spec, [lesson])
    assert contract.baseline is False
    assert lesson.requirement in contract.acceptance
    assert contract.applied_lessons[0].id == "L_1"


def test_unsupported_spec_has_empty_contract():
    spec = JobSpec(
        job_type="unsupported",
        goal="mint nft",
        subject="",
        domain="",
        count=None,
        deliverables=[],
        explicit_requirements=[],
        time_sensitive=False,
        raw="mint nft",
        refusal_reason="nope",
    )
    contract = build_contract(spec, [])
    assert contract.acceptance == []
