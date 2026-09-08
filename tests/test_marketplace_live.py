"""Live-registry semantic acceptance tests (READ-ONLY: only `discover`).

Gated behind PRIOR_LIVE_MARKETPLACE=1 plus buyer credentials in .env.
Values from .env authenticate the read-only lookup only and are never
printed. These tests assert PRODUCT correctness (task suitability), not
ranker self-consistency.
"""

import os

import pytest

LIVE = os.getenv("PRIOR_LIVE_MARKETPLACE") == "1"


def _live_env(monkeypatch):
    from dotenv import dotenv_values
    from pathlib import Path

    values = dotenv_values(str(Path(__file__).resolve().parents[1] / ".env"))
    for key in ("BUYER_WALLET_ADDRESS", "BUYER_WALLET_ID", "BUYER_SIGNER_PRIVATE_KEY"):
        assert values.get(key), f"{key} required for live discovery"
        monkeypatch.setenv(key, values[key])
    monkeypatch.setenv("ACP_ENABLED", "true")
    return values


def _isolated_stores(tmp_path, monkeypatch):
    from prior import jobs, memory, settings

    db = tmp_path / "sibyl-memory.db"
    jobfile = tmp_path / "jobs.json"
    identity_db = tmp_path / "identity.db"
    monkeypatch.setattr(settings, "memory_db_path", lambda: db)
    monkeypatch.setattr(settings, "jobs_path", lambda: jobfile)
    monkeypatch.setattr(settings, "identity_db_path", lambda: identity_db)
    monkeypatch.setattr(memory, "memory_db_path", lambda: db)
    monkeypatch.setattr(jobs, "jobs_path", lambda: jobfile)


def _bridge_guard(monkeypatch):
    import prior.providers.virtuals as virtuals_mod

    seen: list[str] = []
    real = virtuals_mod._bridge

    def _watched(args):
        seen.append(args[0] if args else "")
        return real(args)

    monkeypatch.setattr(virtuals_mod, "_bridge", _watched)
    return seen


pytestmark = pytest.mark.skipif(not LIVE, reason="live marketplace gate not enabled")

RESEARCH_REQUEST = (
    "Research the top five AI wallet companies and compare their features, "
    "pricing, strengths, and weaknesses."
)
MONITOR_REQUEST = "Monitor smart-money wallet activity and report notable movements."
ABSURD_REQUEST = "Calibrate the quantum flux capacitor firmware to 88 terahertz."


def test_live_case_a_and_c_selection_plus_clause(tmp_path, monkeypatch):
    """CASE A + C combined: live research selection, then the exact learned
    clause inside the executable provider input.

    The lesson-bearing contract is replayed against the captured live market
    snapshot that just produced a selection, so propagation is proven
    deterministically while every marketplace byte stays live.
    """
    _live_env(monkeypatch)
    _isolated_stores(tmp_path, monkeypatch)
    seen = _bridge_guard(monkeypatch)
    from prior import lessons as lessons_mod
    from prior import memory as memory_mod
    from prior import service
    from prior.domain import Lesson
    from prior.marketplace import (
        NoCompatibleProvider,
        RESEARCH_TASK_VERBS,
        select_provider_for_spec,
        validate_against_schema,
    )

    ws = "ws_live_ac"
    job = service.specify(ws, RESEARCH_REQUEST)
    snapshot: list[dict] = []

    def _snapshotting(keyword: str) -> list[dict]:
        from prior.marketplace import discover_live
        agents = discover_live(keyword)
        snapshot.extend(agents)
        return agents

    try:
        sel = select_provider_for_spec(job.spec, job.contract, discover=_snapshotting)
    except NoCompatibleProvider as exc:
        assert exc.candidates_seen >= 1 and exc.rejections
        assert set(seen) == {"discover"}
        return
    winner = sel.candidate
    winner_caps = [item["capability"] for item in winner.task_evidence]
    assert any(verb in RESEARCH_TASK_VERBS for verb in winner_caps), (
        f"winner lacks research task evidence: {winner.task_evidence}")
    for item in winner.task_evidence:
        assert item["source"] in ("offering_name", "offering_description", "deliverable"), (
            f"task evidence must be offering-level: {item}")
    for item in winner.subject_evidence:
        assert item["source"] in ("offering_name", "offering_description", "deliverable"), (
            f"subject evidence must be offering-level: {item}")
    schema = winner.requirements_schema
    if schema not in (None, "", {}):
        assert validate_against_schema(
            sel.requirement_preview["requirement_data"], schema) == []

    clause = "Include an explicit side-by-side comparison whenever multiple products are requested."
    memory_mod.write_lesson(ws, Lesson(
        id="L_live", workspace_id=ws, job_type="research", issue="comparison",
        requirement=clause, reason="live gate", status="active",
        created_at=lessons_mod.now_iso(),
    ))
    job2 = service.specify(
        ws,
        "Research the top 5 AI wallet companies and compare features, prices, "
        "strengths and weaknesses.")
    assert clause in [lesson.requirement for lesson in job2.contract.applied_lessons]
    assert snapshot, "live snapshot must be captured for replay"
    sel2 = select_provider_for_spec(
        job2.spec, job2.contract, discover=lambda keyword: list(snapshot))
    preview = sel2.requirement_preview["requirement_data"]
    blob = " ".join(str(value) for value in preview.values() if isinstance(value, str))
    assert clause in blob, "learned clause missing from executable provider input"
    assert clause in sel2.requirement_preview["learned_requirements"]
    assert set(seen) == {"discover"}


def test_live_case_a_rejects_wallet_tracking_offering(tmp_path, monkeypatch):
    """CASE A companion: a tracking-only offering must not be selectable."""
    _live_env(monkeypatch)
    _isolated_stores(tmp_path, monkeypatch)
    _bridge_guard(monkeypatch)
    from prior import service
    from prior.marketplace import (
        check_compatibility,
        discover_live,
        normalize_agents,
        select_provider_for_spec,
    )
    from prior.marketplace import build_capability_query

    job = service.specify("ws_live_a2", RESEARCH_REQUEST)
    query = build_capability_query(job.spec, job.contract)
    candidates, _, _ = normalize_agents(discover_live(query.primary_keyword))
    tracking = [c for c in candidates
                if (c.offering_name or "").lower() == "smartmoneytracking"]
    if not tracking:
        pytest.skip("smartMoneyTracking not in current market snapshot")
    for candidate in tracking:
        ok, reason = check_compatibility(candidate, query, job.contract, job.spec)
        assert not ok, f"tracking offering wrongly compatible: {reason}"
        assert reason, "rejection must carry a truthful reason"


def test_live_case_b_monitoring_differs_from_research(tmp_path, monkeypatch):
    """CASE B: a monitoring request must derive monitoring capabilities."""
    _live_env(monkeypatch)
    _isolated_stores(tmp_path, monkeypatch)
    _bridge_guard(monkeypatch)
    from prior import service
    from prior.marketplace import (
        NoCompatibleProvider,
        build_capability_query,
        select_provider_for_spec,
    )

    job_r = service.specify("ws_live_b1", RESEARCH_REQUEST)
    job_m = service.specify("ws_live_b2", MONITOR_REQUEST)
    query_r = build_capability_query(job_r.spec, job_r.contract)
    query_m = build_capability_query(job_m.spec, job_m.contract)
    assert set(query_r.task_capabilities) == {"research", "compare"}
    assert "monitor" in query_m.task_capabilities
    assert set(query_m.task_capabilities) != set(query_r.task_capabilities)
    try:
        sel = select_provider_for_spec(job_m.spec, job_m.contract)
    except NoCompatibleProvider as exc:
        assert exc.candidates_seen >= 1 and exc.rejections
        return
    assert sel.candidate.task_evidence, "selected monitoring provider must show task evidence"
    evidence_blob = " ".join(
        [item["capability"] for item in sel.candidate.task_evidence] + [
            sel.candidate.offering_name or "", sel.candidate.agent_name or ""]).lower()
    assert any(tok in evidence_blob for tok in (
        "monitor", "track", "report", "scan", "detect", "screen",
        "watch", "alert", "ranking", "flow", "movements", "activity")), (
        f"monitoring selection lacks monitoring evidence: {sel.candidate.task_evidence}")


def test_live_case_c_lesson_recall_and_live_attempt(tmp_path, monkeypatch):
    """CASE C: real isolated recall is proven; the live attempt is recorded
    truthfully whether it selects or no-matches (market churn is real)."""
    _live_env(monkeypatch)
    _isolated_stores(tmp_path, monkeypatch)
    _bridge_guard(monkeypatch)
    from prior import lessons as lessons_mod
    from prior import memory as memory_mod
    from prior import service
    from prior.domain import Lesson
    from prior.marketplace import NoCompatibleProvider, select_provider_for_spec

    ws = "ws_live_c"
    clause = "Include an explicit side-by-side comparison whenever multiple products are requested."
    memory_mod.write_lesson(ws, Lesson(
        id="L_live", workspace_id=ws, job_type="research", issue="comparison",
        requirement=clause, reason="live gate", status="active",
        created_at=lessons_mod.now_iso(),
    ))
    job = service.specify(
        ws, "Research the top five decentralized exchanges and compare their features and pricing.")
    assert clause in [lesson.requirement for lesson in job.contract.applied_lessons]
    try:
        sel = select_provider_for_spec(job.spec, job.contract)
    except NoCompatibleProvider as exc:
        assert exc.candidates_seen >= 1 and exc.rejections
        return
    preview = sel.requirement_preview["requirement_data"]
    blob = " ".join(str(value) for value in preview.values() if isinstance(value, str))
    assert clause in blob, "learned clause missing from executable provider input"
    assert clause in sel.requirement_preview["learned_requirements"]


def test_live_case_d_unsupported_task_has_no_match(tmp_path, monkeypatch):
    """CASE D: a task no offering can perform returns truthful no-match."""
    _live_env(monkeypatch)
    _isolated_stores(tmp_path, monkeypatch)
    seen = _bridge_guard(monkeypatch)
    from prior import service
    from prior.marketplace import NoCompatibleProvider, select_provider_for_spec

    job = service.specify("ws_live_d", ABSURD_REQUEST)
    with pytest.raises(NoCompatibleProvider) as exc:
        select_provider_for_spec(job.spec, job.contract)
    assert exc.value.candidates_seen >= 1
    assert exc.value.rejections
    assert set(seen) == {"discover"}
