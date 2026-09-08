"""Marketplace semantic-compatibility tests on fixture data.

No network, no ACP calls (bridge access raises). Covers the corrected
model: task-vs-subject separation, hard task gates, schema receivability
with local validation, malformed fail-closed, funds/chain policy.
"""

import pytest

from prior.contract import build_contract
from prior.job_spec import parse_job
from prior.marketplace import (
    NoCompatibleProvider,
    build_capability_query,
    build_requirement_data,
    check_compatibility,
    check_task_fit,
    normalize_agents,
    rank_candidates,
    schema_required_fields,
    select_provider_for_spec,
    validate_against_schema,
)


@pytest.fixture
def no_bridge(monkeypatch):
    import prior.providers.virtuals as virtuals_mod

    def _boom(args):
        raise AssertionError(f"fixture test must not touch the bridge: {args}")

    monkeypatch.setattr(virtuals_mod, "_bridge", _boom)


def _agent(name, wallet, offerings, **kw):
    return {
        "id": f"id-{name}", "name": name,
        "description": kw.get("description", ""),
        "walletAddress": wallet,
        "lastActiveAt": kw.get("lastActiveAt", "2026-09-01T00:00:00Z"),
        "rating": kw.get("rating", 4.0), "isHidden": kw.get("isHidden", False),
        "offerings": offerings,
    }


def _offering(name, **kw):
    return {
        "name": name,
        "description": kw.get("description", ""),
        "requirements": kw.get("requirements", {}),
        "deliverable": kw.get("deliverable", ""),
        "priceType": kw.get("priceType", "fixed"),
        "priceValue": kw.get("priceValue", 1.0),
        "requiredFunds": kw.get("requiredFunds", False),
        "slaMinutes": kw.get("slaMinutes", 60),
        "isHidden": kw.get("isHidden", False),
        "isPrivate": kw.get("isPrivate", False),
    }


def _research(text="Research the top five AI wallet companies and compare their features."):
    spec = parse_job(text)
    return spec, build_contract(spec, []), build_capability_query(spec, build_contract(spec, []))


def _chains(*ids):
    return [{"chainId": cid} for cid in ids]


def test_task_verbs_survive_capability_derivation():
    spec, contract, query = _research()
    assert "research" in query.task_capabilities
    assert "compare" in query.task_capabilities
    assert "wallet" in query.subject_terms or "wallets" in query.subject_terms
    assert "research" not in query.subject_terms


def test_subject_word_alone_does_not_pass_task_gate():
    _, _, query = _research()
    agents = [_agent("Einstein", "0x" + "aa" * 20, [
        _offering("smartMoneyTracking",
                  description="Top trader wallets re-ranked by alpha quality with verdicts and scores.")],
        description="On-chain wallet analytics and tracking data.")]
    cands, _, _ = normalize_agents(agents)
    ok, reason, _ = check_task_fit(cands[0], query)
    assert not ok
    assert "task" in reason


def test_brief_slot_schema_passes_and_validates(no_bridge):
    spec, contract, query = _research()
    agents = [_agent("Researcher", "0x" + "bb" * 20, [
        _offering("market research",
                  description="Autonomous research and intelligence gathering with structured reports on any topic.",
                  requirements={"type": "object", "required": ["query"],
                                "properties": {
                                    "query": {"type": "string"},
                                    "depth": {"type": "string", "default": "standard"}}})],
        description="Research services.")]
    agents[0]["chains"] = _chains(8453)
    sel = select_provider_for_spec(spec, contract, discover=lambda kw: agents)
    assert sel.candidate.offering_name == "market research"
    data = sel.requirement_preview["requirement_data"]
    assert "query" in data and data.get("depth") == "standard"
    assert validate_against_schema(data, agents[0]["offerings"][0]["requirements"]) == []


def test_schema_without_brief_slot_rejects_even_with_subject_overlap(no_bridge):
    spec, contract, query = _research()
    agents = [_agent("Tracker", "0x" + "cc" * 20, [
        _offering("wallet tracking",
                  description="Research-grade wallet data with verdicts and scores.",
                  requirements={"type": "object",
                                "properties": {
                                    "days": {"type": "number"},
                                    "chain": {"type": "string"},
                                    "limit": {"type": "number"}}})],
        description="Wallet research analytics.")]
    agents[0]["chains"] = _chains(8453)
    with pytest.raises(NoCompatibleProvider) as exc:
        select_provider_for_spec(spec, contract, discover=lambda kw: agents)
    assert any("no field for the task brief" in reason for _, reason in exc.value.rejections)


def test_malformed_schema_fails_closed(no_bridge):
    spec, contract, _ = _research()
    agents = [_agent("Foggy", "0x" + "dd" * 20, [
        _offering("deep research",
                  description="We research and compare any topic.",
                  requirements="{not valid json{{")])]
    agents[0]["chains"] = _chains(8453)
    with pytest.raises(NoCompatibleProvider) as exc:
        select_provider_for_spec(spec, contract, discover=lambda kw: agents)
    assert any("could not be safely interpreted" in reason for _, reason in exc.value.rejections)


def test_required_funds_filtered(no_bridge):
    spec, contract, _ = _research()
    agents = [_agent("Funder", "0x" + "ee" * 20, [
        _offering("deep research",
                  description="We research and compare every topic in depth.",
                  requirements={"type": "object",
                                "properties": {"topic": {"type": "string"}}},
                  requiredFunds=True)])]
    agents[0]["chains"] = _chains(8453)
    with pytest.raises(NoCompatibleProvider) as exc:
        select_provider_for_spec(spec, contract, discover=lambda kw: agents)
    assert any("fund-transfer" in reason for _, reason in exc.value.rejections)


def test_wrong_chain_filtered(no_bridge):
    spec, contract, _ = _research()
    agents = [_agent("FarAway", "0x" + "ff" * 20, [
        _offering("deep research",
                  description="We research and compare every topic in depth.",
                  requirements={"type": "object",
                                "properties": {"topic": {"type": "string"}}})])]
    agents[0]["chains"] = _chains(1)
    with pytest.raises(NoCompatibleProvider) as exc:
        select_provider_for_spec(spec, contract, discover=lambda kw: agents)
    assert any("chain path" in reason for _, reason in exc.value.rejections)


def test_monitoring_family_accepts_tracker_naming(no_bridge):
    spec = parse_job("Monitor smart-money wallet activity and report notable movements.")
    contract = build_contract(spec, [])
    query = build_capability_query(spec, contract)
    assert "monitor" in query.task_capabilities
    agents = [_agent("Einstein", "0x" + "aa" * 20, [
        _offering("smartMoneyTracking",
                  description="Top trader wallets ranked with verdicts and flow conviction.")],
        description="On-chain analytics.")]
    agents[0]["chains"] = _chains(8453)
    cands, _, _ = normalize_agents(agents)
    ok, _, evidence = check_task_fit(cands[0], query)
    assert ok and evidence

def test_sentinel_future_timestamp_earns_no_recency():
    from prior.marketplace import score_candidate
    _, _, query = _research()
    agents = [_agent("TimeTraveler", "0x" + "11" * 20,
                     [_offering("market research", description="research reports")],
                     lastActiveAt="2999-12-31T00:00:00.000Z", rating=5.0)]
    cands, _, _ = normalize_agents(agents)
    _, breakdown = score_candidate(cands[0], query)
    assert breakdown["recency_note"] == "suspicious future timestamp, ignored"


def test_enum_and_type_validation_rejects_bad_preview():
    schema = {"type": "object", "required": ["topic"],
              "properties": {"topic": {"type": "string", "enum": ["x", "y"]}}}
    assert validate_against_schema({"topic": "z"}, schema) != []
    assert validate_against_schema({"topic": "x"}, schema) == []
    assert validate_against_schema({"n": "s"}, {"type": "object",
                                                "properties": {"n": {"type": "number"}}}) != []


def test_rating_never_compensates_failed_task_gate(no_bridge):
    spec, contract, _ = _research()
    agents = [
        _agent("Irrelevant Star", "0x" + "22" * 20,
               [_offering("meme coins", description="Meme token generation service.")],
               rating=5.0, lastActiveAt="2026-09-07T00:00:00Z"),
        _agent("Solid Researcher", "0x" + "33" * 20,
               [_offering("market research",
                          description="We research and compare any topic in depth with reports.",
                          requirements={"type": "object", "required": ["topic"],
                                        "properties": {"topic": {"type": "string"}}})],
               rating=3.0, lastActiveAt="2026-09-07T00:00:00Z"),
    ]
    for agent in agents:
        agent["chains"] = _chains(8453)
    sel = select_provider_for_spec(spec, contract, discover=lambda kw: agents)
    assert sel.candidate.agent_name == "Solid Researcher"


def test_malformed_entries_skipped_not_invented():
    cands, seen, skipped = normalize_agents([
        None, "junk", {"name": "NoWallet"},
        {"name": "NoOfferings", "walletAddress": "0x1234"},
    ])
    assert seen == 4 and cands == [] and skipped == 4


def test_discovery_failure_is_explicit():
    spec, contract, _ = _research()

    def _boom(keyword):
        raise RuntimeError("network down")

    from prior.marketplace import DiscoveryError, select_provider_for_spec as sel
    with pytest.raises(DiscoveryError):
        sel(spec, contract, discover=_boom)
    with pytest.raises(DiscoveryError):
        sel(spec, contract, discover=lambda kw: {"not": "a list"})


def test_schema_required_names_still_checked():
    assert "quantum_entanglement_proof" in schema_required_fields(
        {"required": ["quantum_entanglement_proof"]})
    assert schema_required_fields({}) == []


def test_ranking_deterministic_and_merit_ordered():
    _, _, query = _research()
    agents = [
        _agent("B Research", "0x" + "bb" * 20,
               [_offering("market research", description="research and compare reports on any topic")],
               rating=3.0, lastActiveAt="2026-09-01T00:00:00Z"),
        _agent("A Research", "0x" + "aa" * 20,
               [_offering("market research", description="research and compare reports on any topic")],
               rating=4.5, lastActiveAt="2026-09-06T00:00:00Z"),
    ]
    cands, _, _ = normalize_agents(agents)
    first = rank_candidates(cands, query)
    second = rank_candidates(list(reversed(cands)), query)
    assert [c.wallet_address for c, _, _ in first] == [c.wallet_address for c, _, _ in second]
    assert first[0][0].agent_name == "A Research"
