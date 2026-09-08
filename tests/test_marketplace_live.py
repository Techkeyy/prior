"""Live-registry marketplace tests (READ-ONLY: only `discover` calls).

Gated behind PRIOR_LIVE_MARKETPLACE=1 plus buyer credentials in .env.
Values from .env are used for authentication only and never printed.
-skippable anywhere; run explicitly for the read-only discovery gate.
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


def test_live_generic_research_finds_compatible_providers(tmp_path, monkeypatch):
    _live_env(monkeypatch)
    _isolated_stores(tmp_path, monkeypatch)
    seen = _bridge_guard(monkeypatch)
    from prior import service
    from prior.marketplace import select_provider_for_spec

    job = service.specify(
        "ws_live_a",
        "Research the top five AI wallet companies and compare their features, pricing, strengths, and weaknesses.",
    )
    sel = select_provider_for_spec(job.spec, job.contract)
    assert sel.compatible_total >= 1
    assert sel.candidate.offering_name
    assert sel.candidate.wallet_address.startswith("0x")
    assert sel.score_breakdown["score"] == sel.score
    assert set(seen) == {"discover"}


def test_live_learned_clause_reaches_provider_payload(tmp_path, monkeypatch):
    _live_env(monkeypatch)
    _isolated_stores(tmp_path, monkeypatch)
    _bridge_guard(monkeypatch)
    from prior import lessons as lessons_mod
    from prior import memory as memory_mod
    from prior import service
    from prior.domain import Lesson
    from prior.marketplace import select_provider_for_spec

    ws = "ws_live_b"
    clause = "Include an explicit side-by-side comparison whenever multiple products are requested."
    memory_mod.write_lesson(ws, Lesson(
        id="L_live", workspace_id=ws, job_type="research", issue="comparison",
        requirement=clause, reason="live gate", status="active",
        created_at=lessons_mod.now_iso(),
    ))
    job = service.specify(
        ws, "Research the top five decentralized exchanges and compare their features and pricing.")
    assert clause in [lesson.requirement for lesson in job.contract.applied_lessons]
    sel = select_provider_for_spec(job.spec, job.contract)
    assert clause in sel.requirement_preview["learned_requirements"]
    assert clause in sel.requirement_preview["job_description"]


def test_live_selection_is_merit_argmax_not_hardcoded(tmp_path, monkeypatch):
    values = _live_env(monkeypatch)
    _isolated_stores(tmp_path, monkeypatch)
    _bridge_guard(monkeypatch)
    from prior import service
    from prior.marketplace import (
        build_capability_query,
        check_compatibility,
        discover_live,
        normalize_agents,
        rank_candidates,
        select_provider_for_spec,
    )

    job = service.specify(
        "ws_live_c", "Research the top five AI wallet companies and compare their features.")
    sel = select_provider_for_spec(job.spec, job.contract)

    # Independent recomputation inside the test: winner must be the argmax.
    query = build_capability_query(job.spec, job.contract)
    candidates, _, _ = normalize_agents(discover_live(query.primary_keyword))
    compatible = [c for c in candidates if check_compatibility(c, query)[0]]
    expected = rank_candidates(compatible, query)[0]
    assert sel.candidate.wallet_address == expected[0].wallet_address
    assert sel.candidate.offering_name == expected[0].offering_name

    # Seller parity: the known seller gets no preference. Remove it and the
    # winner must be unchanged, unless the seller itself won on merit.
    seller_wallet = (values.get("SELLER_WALLET_ADDRESS") or "").strip()
    assert seller_wallet, "seller wallet required for parity check"
    rest = [c for c in compatible if c.wallet_address.lower() != seller_wallet.lower()]
    if sel.candidate.wallet_address.lower() != seller_wallet.lower():
        assert rank_candidates(rest, query)[0][0].wallet_address == sel.candidate.wallet_address
    else:
        runner_up = rank_candidates(rest, query)[0][1] if rest else 0.0
        assert sel.score > runner_up
