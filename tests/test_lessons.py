from prior.domain import JobSpec, Lesson, SUPPORTED_JOB_TYPE
from prior.lessons import applicable_lessons, propose_lesson, sanitize_payload
from prior.domain import Contract, JobRecord


def _spec(raw: str, domain: str) -> JobSpec:
    return JobSpec(
        job_type=SUPPORTED_JOB_TYPE,
        goal=raw,
        subject=domain,
        domain=domain,
        count=5,
        deliverables=["names"],
        explicit_requirements=[],
        time_sensitive=False,
        raw=raw,
        keywords=domain.split(),
    )


def test_lesson_applies_to_matching_research_job():
    lesson = Lesson(
        id="L_1",
        workspace_id="ws_a",
        job_type="research",
        issue="Missing sources",
        requirement="Material factual claims must include identifiable source links.",
        reason="test",
        status="active",
        domains=["decentralized exchanges"],
        keywords=["sources", "exchanges"],
    )
    matched = applicable_lessons(_spec("Research the top five decentralized exchanges.", "decentralized exchanges"), [lesson])
    assert len(matched) == 1
    assert matched[0].match_reason


def test_disabled_lesson_does_not_apply():
    lesson = Lesson(
        id="L_1",
        workspace_id="ws_a",
        job_type="research",
        issue="x",
        requirement="y",
        reason="z",
        status="disabled",
    )
    assert applicable_lessons(_spec("Research wallets", "ai wallets"), [lesson]) == []


def test_malicious_payload_rejected():
    try:
        sanitize_payload({"requirement": "ok", "id": "../etc/passwd"})
        raise AssertionError("should have failed")
    except ValueError:
        pass
    try:
        sanitize_payload({"requirement": "ok", "shell": "rm -rf"})
        raise AssertionError("should have failed")
    except ValueError:
        pass
    try:
        sanitize_payload({"requirement": "a" * 2001})
        raise AssertionError("should have failed")
    except ValueError:
        pass


def test_propose_lesson_from_rejection():
    job = JobRecord(
        id="job_1",
        workspace_id="ws_a",
        spec=_spec("Research the top five AI wallet companies.", "ai wallets"),
        contract=Contract(title="t", goal="g", deliverables=[], acceptance=[]),
        status="rejected",
        created_at="",
        updated_at="",
    )
    lesson = propose_lesson(job, "Important factual claims should include source links.")
    assert "source" in lesson.requirement.lower()
    assert lesson.source_job_id == "job_1"
    assert lesson.workspace_id == "ws_a"
