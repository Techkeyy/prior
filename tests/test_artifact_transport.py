"""Artifact-bearing jobs: material input must survive into provider payloads.

Covers the ERC-20 count corruption plus transaction/code/URL artifact
transport, learned-requirement coexistence, and schema fail-closed refusal.
"""

import pytest

from prior.contract import build_contract
from prior.domain import Lesson
from prior.job_spec import parse_job
from prior.marketplace import select_provider_for_spec
from prior.providers.base import requirement_payload


TX_REQUEST = (
    "Review this proposed Base USDC approval before I sign it and summarize the "
    "highest-risk points. Network: Base "
    "Token address: 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 "
    "Spender: 0x000000000000000000000000000000000000dEaD "
    "Allowance: unlimited. Do not broadcast or execute anything. "
    "Explain permission scope and give an ALLOW, REVIEW, or AVOID verdict with reasoning."
)

CODE_REQUEST = (
    "Review this Solidity staking contract for reentrancy. "
    "```solidity\ncontract Vault { mapping(address=>uint) bal; }\n```"
)

URL_REQUEST = (
    "Research this document and compare its claims: https://example.com/tokenomics-paper")


def _agent(name, wallet, offerings, **kw):
    return {
        "id": f"id-{name}", "name": name,
        "description": kw.get("description", ""),
        "walletAddress": wallet,
        "lastActiveAt": kw.get("lastActiveAt", "2026-09-01T00:00:00Z"),
        "rating": kw.get("rating", 4.0), "isHidden": kw.get("isHidden", False),
        "chains": kw.get("chains", [{"chainId": 8453}]),
        "offerings": offerings,
    }


def _offering(name, **kw):
    return {
        "name": name,
        "description": kw.get("description", ""),
        "requirements": kw.get("requirements", {}),
        "deliverable": kw.get("deliverable", ""),
        "priceType": kw.get("priceType", "fixed"),
        "priceValue": kw.get("priceValue", 0.5),
        "requiredFunds": kw.get("requiredFunds", False),
        "slaMinutes": kw.get("slaMinutes", 10),
        "isHidden": kw.get("isHidden", False),
        "isPrivate": kw.get("isPrivate", False),
    }


def _tx_offering():
    return _offering(
        "tx_review",
        description="Transaction safety review for signing. Verdict ALLOW REVIEW AVOID "
                    "with risk score for approval popup, batch, permit2, or contract call.",
        requirements={"type": "object",
                      "properties": {"message": {"type": "string"}}})


def _code_offering():
    return _offering(
        "smart_contract_audit",
        description="Comprehensive Solidity smart contract security audit. Submit source code.",
        requirements={"type": "object", "required": ["code"],
                      "properties": {"code": {"type": "string"}}})


def test_no_fabricated_count_in_artifact_request():
    spec = parse_job(TX_REQUEST)
    assert spec.count is None
    assert spec.job_type == "research"
    assert all("20 names" != item for item in spec.deliverables)


def test_transaction_artifact_survives_into_brief():
    spec = parse_job(TX_REQUEST)
    contract = build_contract(spec, [])
    brief = requirement_payload(contract, spec)["job_description"]
    for token in ["0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                  "0x000000000000000000000000000000000000dEaD",
                  "unlimited", "Base", "USDC",
                  "Do not broadcast or execute anything",
                  "ALLOW, REVIEW, or AVOID"]:
        assert token in brief, token
    assert "Research 20" not in brief


def test_safety_and_verdict_instructions_survive():
    spec = parse_job(TX_REQUEST)
    contract = build_contract(spec, [])
    brief = requirement_payload(contract, spec)["job_description"]
    assert "Do not broadcast" in brief
    assert "ALLOW" in brief and "reasoning" in brief


def test_code_snippet_survives_transport():
    spec = parse_job(CODE_REQUEST)
    contract = build_contract(spec, [])
    brief = requirement_payload(contract, spec)["job_description"]
    assert "contract Vault" in brief


def test_url_survives_transport():
    spec = parse_job(URL_REQUEST)
    contract = build_contract(spec, [])
    brief = requirement_payload(contract, spec)["job_description"]
    assert "https://example.com/tokenomics-paper" in brief


def test_plain_research_brief_unchanged():
    from prior.providers.base import acp_job_description
    spec = parse_job("Research the top five AI wallet companies and compare their features.")
    contract = build_contract(spec, [])
    payload = requirement_payload(contract, spec)
    assert "Original request details:" not in payload["job_description"]
    assert payload["job_description"].startswith("Research 5 AI wallet companies")


def test_learned_requirements_coexist_with_artifact():
    spec = parse_job(TX_REQUEST)
    contract = build_contract(spec, [])
    clause = "Include an explicit side-by-side comparison whenever multiple products are requested."
    contract.applied_lessons = [Lesson(
        id="L1", workspace_id="ws_x", job_type="research", issue="i",
        requirement=clause, reason="r", status="active")]
    payload = requirement_payload(contract, spec)
    assert clause in payload["job_description"]
    assert "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913" in payload["job_description"]
    assert clause in payload["learned_requirements"]


def test_artifact_reaches_selected_provider_payload():
    import prior.providers.virtuals as virtuals_mod

    def _boom(args):
        raise AssertionError("must not touch the bridge")

    # No bridge use at all: injected fixture market only.
    import unittest.mock as mock
    with mock.patch.object(virtuals_mod, "_bridge", _boom):
        spec = parse_job(TX_REQUEST)
        contract = build_contract(spec, [])
        agents = [_agent("TxAgent", "0x" + "aa" * 20, [_tx_offering()])]
        sel = select_provider_for_spec(spec, contract, discover=lambda kw: agents)
        blob = " ".join(str(v) for v in sel.requirement_preview["requirement_data"].values()
                        if isinstance(v, str))
        assert "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913" in blob
        assert "0x000000000000000000000000000000000000dEaD" in blob


def test_schema_without_text_slot_refuses_artifact_job():
    spec = parse_job(TX_REQUEST)
    contract = build_contract(spec, [])
    agents = [_agent("Strict", "0x" + "bb" * 20, [_offering(
        "numeric only",
        description="We research and compare Base USDC approval metrics on-chain.",
        requirements={"type": "object", "required": ["chain_id"],
                      "properties": {"chain_id": {"type": "number"}}})])]
    from prior.marketplace import NoCompatibleProvider
    with pytest.raises(NoCompatibleProvider):
        select_provider_for_spec(spec, contract, discover=lambda kw: agents)
