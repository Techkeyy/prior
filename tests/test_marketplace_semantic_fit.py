"""Semantic-fit regressions: source-code auditors vs transaction reviews.

Production evidence (job_53fe89052b5b / BitsAndBytesBack security_audit,
score 13.0 beating the tx-review specialist at 12.0): a code-only
vulnerability scanner won a wallet-approval review request on name-term +
rating. Compatibility must be semantic; rating may only rank candidates
that already passed compatibility. Sellers here are fixture archetypes,
never live identities; the implementation contains no name/wallet logic.
"""

import pytest

from prior.job_spec import parse_job
from prior.contract import build_contract
from prior.marketplace import (
    NoCompatibleProvider,
    build_capability_query,
    check_compatibility,
    rank_candidates,
    select_provider_for_spec,
)
from tests.test_marketplace import _agent, _offering  # fixture factories


@pytest.fixture
def no_bridge(monkeypatch):
    import prior.providers.virtuals as virtuals_mod

    def _boom(args):
        raise AssertionError(f"fixture test must not touch the bridge: {args}")

    monkeypatch.setattr(virtuals_mod, "_bridge", _boom)


TX_REQUEST = (
    "Review this proposed Base USDC approval before I sign it and identify "
    "the security risks.\n\nThis is a controlled review only. Do not "
    "broadcast, sign, or execute anything.\n\nNetwork: Base\nToken: USDC\n"
    "Token address: 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913\n"
    "Action: ERC-20 token approval\n"
    "Spender: 0x3333333333333333333333333333333333333333\nAllowance: 50 USDC\n\n"
    "Explain exactly what permission this approval would give the spender, "
    "use every transaction field provided above, identify the main risks, "
    "and give an ALLOW, REVIEW, or AVOID verdict with reasoning."
)


def _code_auditor(rating=5.0, **over):
    kw = dict(description="Autonomous security audit and vulnerability scanner. "
                          "CVSS-scored findings with severity and remediation.",
              deliverable="JSON report with security_score (0-100), CVSS-scored vulnerabilities",
              requirements={"type": "object", "required": ["code"],
                            "properties": {"code": {"type": "string",
                                                    "description": "Source code to audit for vulnerabilities"}}},
              priceValue=0.05)
    kw.update(over)
    return _offering("security_audit", **kw)


def _tx_specialist(**over):
    kw = dict(description="0.03 USDC transaction safety review for anyone about "
                          "to sign a wallet transaction. Buy this right before "
                          "approving or signing a swap, bridge, token approval "
                          "popup, batch, permit2, or contract call.",
              deliverable="Plain-language ALLOW REVIEW or AVOID verdict grounded in supplied fields",
              requirements={"type": "object",
                            "anyOf": [{"required": ["message"]}],
                            "properties": {"message": {"type": "string"}}},
              priceValue=0.03)
    kw.update(over)
    return _offering("tx_explain_allow_review_avoid", **kw)


def _query_for(text):
    spec = parse_job(text)
    contract = build_contract(spec, [])
    return spec, contract, build_capability_query(spec, contract)


def _cands(*agents):
    from prior.marketplace import normalize_agents
    return normalize_agents(list(agents))[0]


def test_code_only_auditor_is_incompatible_with_transaction_review(no_bridge):
    spec, contract, query = _query_for(TX_REQUEST)
    cand = _cands(_agent("CodeAuditBot", "0x" + "bb" * 20,
                         [_code_auditor(rating=5.0)]))[0]
    ok, reason = check_compatibility(cand, query, contract, spec)
    assert ok is False
    assert "source-code-only auditor" in reason


def test_tx_specialist_remains_compatible(no_bridge):
    spec, contract, query = _query_for(TX_REQUEST)
    cand = _cands(_agent("TxBot", "0x" + "aa" * 20, [_tx_specialist()]))[0]
    ok, reason = check_compatibility(cand, query, contract, spec)
    assert ok is True, reason


def test_rating_cannot_resurrect_incompatible_auditor(no_bridge):
    spec, contract, query = _query_for(TX_REQUEST)
    agents = [_agent("CodeAuditBot", "0x" + "bb" * 20, [_code_auditor(rating=5.0)], rating=5.0)]
    with pytest.raises(NoCompatibleProvider) as exc:
        select_provider_for_spec(spec, contract, discover=lambda kw: agents)
    assert any("source-code-only auditor" in reason for _, reason in exc.value.rejections)


def test_tx_request_prefers_specialist_over_rated_auditor(no_bridge):
    spec, contract, query = _query_for(TX_REQUEST)
    agents = [
        _agent("CodeAuditBot", "0x" + "bb" * 20, [_code_auditor(rating=5.0)], rating=5.0),
        _agent("TxBot", "0x" + "aa" * 20, [_tx_specialist()]),
    ]
    sel = select_provider_for_spec(spec, contract, discover=lambda kw: agents)
    assert sel.candidate.offering_name == "tx_explain_allow_review_avoid"


def test_real_code_audit_request_keeps_auditor_eligible(no_bridge):
    code = "```solidity\ncontract Vault { mapping(address=>uint) bal; }\n```"
    text = ("Review this Solidity staking contract for reentrancy and common "
            "vulnerabilities. " + code)
    spec, contract, query = _query_for(text)
    agents = [_agent("CodeAuditBot", "0x" + "bb" * 20, [_code_auditor()])]
    sel = select_provider_for_spec(spec, contract, discover=lambda kw: agents)
    assert sel.candidate.offering_name == "security_audit"


def test_auditor_still_eligible_when_it_declares_tx_capability(no_bridge):
    spec, contract, query = _query_for(TX_REQUEST)
    hybrid = _code_auditor(
        description="Security audit for smart contracts and wallet transactions, "
                    "including ERC-20 approval and allowance review before signing.")
    agents = [_agent("HybridBot", "0x" + "cc" * 20, [hybrid])]
    sel = select_provider_for_spec(spec, contract, discover=lambda kw: agents)
    assert sel.candidate.offering_name == "security_audit"


def test_generic_research_selection_unchanged(no_bridge):
    spec, contract, query = _query_for(
        "Research the top five AI wallet companies and compare their features.")
    agents = [
        _agent("ResearchBot", "0x" + "dd" * 20,
               [_offering("market research", description="Deep research and landscape comparison of AI wallet companies",
                          requirements={"type": "object", "properties": {"topic": {"type": "string"}}})]),
        _agent("CodeAuditBot", "0x" + "bb" * 20, [_code_auditor(rating=5.0)]),
    ]
    sel = select_provider_for_spec(spec, contract, discover=lambda kw: agents)
    assert sel.candidate.offering_name == "market research"


def test_no_seller_literals_in_semantic_guard():
    from pathlib import Path
    source = Path("src/prior/marketplace.py").read_text(encoding="utf-8")
    for literal in ("BitsAndBytesBack", "COINGAZURA", "coingazura", "0x436f324",
                    "0x66ebcaf", "0x3333333333333333", "security_audit"):
        assert literal not in source


def test_guard_reuses_shared_transaction_review_semantics():
    from pathlib import Path
    source = Path("src/prior/marketplace.py").read_text(encoding="utf-8")
    assert "from prior.job_spec import transaction_review_request" in source
