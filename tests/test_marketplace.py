"""Marketplace layer tests on fixture data (no network, no ACP calls).

Covers: payload clause propagation (B-fixture), non-seller merit win (D),
truthful no-match (E), unsatisfiable schema filter (F), offline/hidden
policy (G), malformed input handling (H), discovery failure (I).
Live-registry tests live in test_marketplace_live.py.
"""

import pytest

from prior.contract import build_contract
from prior.domain import Contract
from prior.job_spec import parse_job
from prior.marketplace import (
    DiscoveryError,
    NoCompatibleProvider,
    build_capability_query,
    build_provider_payload,
    check_compatibility,
    normalize_agents,
    rank_candidates,
    schema_required_fields,
    select_provider_for_spec,
)


def _agent(name, wallet, offerings, **kw):
    agent = {
        "id": f"id-{name}", "name": name,
        "description": kw.get("description", "general research services"),
        "walletAddress": wallet,
        "lastActiveAt": kw.get("lastActiveAt", "2026-09-01T00:00:00Z"),
        "rating": kw.get("rating", 4.0), "isHidden": kw.get("isHidden", False),
        "offerings": offerings,
    }
    return agent


def _offering(name, **kw):
    return {
        "name": name,
        "description": kw.get("description", "research reports with sources"),
        "requirements": kw.get("requirements", {}),
        "deliverable": kw.get("deliverable", "report"),
        "priceType": kw.get("priceType", "fixed"),
        "priceValue": kw.get("priceValue", 1.0),
        "requiredFunds": kw.get("requiredFunds", False),
        "slaMinutes": kw.get("slaMinutes", 60),
        "isHidden": kw.get("isHidden", False),
        "isPrivate": kw.get("isPrivate", False),
    }


def _spec_contract(text="Research the top five AI wallet companies and compare their features."):
    spec = parse_job(text)
    return spec, build_contract(spec, [])


@pytest.fixture
def no_bridge(monkeypatch):
    import prior.providers.virtuals as virtuals_mod

    def _boom(args):
        raise AssertionError(f"fixture test must not touch the bridge: {args}")

    monkeypatch.setattr(virtuals_mod, "_bridge", _boom)


def test_capability_query_derives_only_from_request():
    spec, contract = _spec_contract()
    query = build_capability_query(spec, contract)
    assert "wallet" in query.required_terms or "wallets" in query.required_terms
    assert query.job_type == "research"
    assert "quantum" not in query.required_terms + query.useful_terms


def test_payload_carries_exact_learned_clause(no_bridge):
    from prior.domain import Lesson
    spec, contract = _spec_contract()
    clause = "Include an explicit side-by-side comparison whenever multiple products are requested."
    contract.applied_lessons = [Lesson(
        id="L1", workspace_id="ws_x", job_type="research", issue="i",
        requirement=clause, reason="r", status="active",
    )]
    agents = [_agent("Wallet Researcher", "0x" + "aa" * 20,
                     [_offering("wallet comparison", description="compare crypto wallets side by side")])]
    sel = select_provider_for_spec(spec, contract, discover=lambda kw: agents)
    assert clause in sel.requirement_preview["learned_requirements"]
    assert clause in sel.requirement_preview["job_description"]
    assert sel.requirement_preview["selected_offering"]["offering_name"] == "wallet comparison"


def test_stronger_nonseller_wins_on_merit():
    spec, contract = _spec_contract()
    agents = [
        _agent("Prior Research", "0x" + "bb" * 20,
               [_offering("general research")], rating=3.0,
               lastActiveAt="2025-01-01T00:00:00Z"),
        _agent("Wallet Specialist", "0x" + "cc" * 20,
               [_offering("wallet comparison",
                          description="compare crypto wallets features pricing side by side")],
               rating=4.8, lastActiveAt="2026-09-05T00:00:00Z"),
    ]
    sel = select_provider_for_spec(spec, contract, discover=lambda kw: agents)
    assert sel.candidate.agent_name == "Wallet Specialist"
    assert sel.candidate.wallet_address != "0x" + "bb" * 20


def test_no_match_is_truthful_and_retryable():
    spec, contract = _spec_contract()
    agents = [_agent("Ghost", "0x" + "dd" * 20,
                     [_offering("Hidden", isHidden=True)])]
    with pytest.raises(NoCompatibleProvider) as exc:
        select_provider_for_spec(spec, contract, discover=lambda kw: agents)
    assert "No compatible Virtuals agent" in str(exc.value)
    assert exc.value.candidates_seen == 1
    assert exc.value.rejections


def test_unsatisfiable_schema_filtered_with_reason():
    spec, contract = _spec_contract()
    agents = [_agent("Strict", "0x" + "ee" * 20,
                     [_offering("Strict Research",
                                requirements={"type": "object",
                                              "required": ["quantum_entanglement_proof"]})])]
    assert schema_required_fields(agents[0]["offerings"][0]["requirements"]) == ["quantum_entanglement_proof"]
    with pytest.raises(NoCompatibleProvider) as exc:
        select_provider_for_spec(spec, contract, discover=lambda kw: agents)
    assert any("cannot supply" in reason for _, reason in exc.value.rejections)


def test_hidden_and_stale_policy():
    spec, contract = _spec_contract()
    query = build_capability_query(spec, contract)
    hidden_agent = _agent("Hidden", "0x" + "11" * 20, [_offering("wallet research")], isHidden=True)
    stale = _agent("Stale", "0x" + "22" * 20, [_offering("wallet research")],
                   lastActiveAt="2024-01-01T00:00:00Z", rating=4.0)
    fresh = _agent("Fresh", "0x" + "33" * 20, [_offering("wallet research")],
                   lastActiveAt="2026-09-07T00:00:00Z", rating=4.0)
    cands, seen, skipped = normalize_agents([hidden_agent, stale, fresh])
    assert seen == 3 and len(cands) == 3
    ok_hidden, _ = check_compatibility(cands[0], query)
    assert not ok_hidden
    ranked = rank_candidates([cands[1], cands[2]], query)
    assert ranked[0][0].agent_name == "Fresh"
    assert ranked[1][2]["recency_note"] == "inactive over 30 days"


def test_malformed_entries_skipped_not_invented():
    cands, seen, skipped = normalize_agents([
        None, "junk", {"name": "NoWallet"},
        {"name": "NoOfferings", "walletAddress": "0x1234"},
        _agent("Good", "0x" + "44" * 20, [_offering("wallet research")]),
    ])
    assert seen == 5
    assert len(cands) == 1
    assert skipped == 4
    assert cands[0].rating is None or isinstance(cands[0].rating, float)
    cands2, _, _ = normalize_agents("not-a-list")
    assert cands2 == []


def test_discovery_failure_is_explicit():
    spec, contract = _spec_contract()

    def _boom(keyword):
        raise RuntimeError("network down")

    with pytest.raises(DiscoveryError):
        select_provider_for_spec(spec, contract, discover=_boom)

    with pytest.raises(DiscoveryError):
        select_provider_for_spec(spec, contract, discover=lambda kw: {"not": "a list"})


def test_fixture_selection_touches_no_bridge(no_bridge):
    spec, contract = _spec_contract()
    agents = [_agent("Wallet Researcher", "0x" + "aa" * 20, [_offering("wallet comparison")])]
    sel = select_provider_for_spec(spec, contract, discover=lambda kw: agents)
    assert sel.compatible_total == 1
    payload = build_provider_payload(sel.candidate, contract, spec)
    assert payload["selected_offering"]["provider_wallet"] == "0x" + "aa" * 20
