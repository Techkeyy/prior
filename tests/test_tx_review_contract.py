"""Transaction-review semantic routing into the contract.

Regression for the ACP 77892 contract-mismatch audit: an ERC-20 approval
security review fell through job_spec._deliverables() to the generic
company-research defaults (names/products/pricing/strengths/weaknesses),
so the user-facing contract described the wrong job even though the
worker brief carried the real request. Detection now shares the job_spec
semantic layer that already governs artifact truthfulness.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prior.contract import build_contract
from prior.job_spec import (
    missing_review_artifact,
    parse_job,
    transaction_review_request,
)
from prior.providers.base import requirement_payload

APPROVAL_REQUEST = (
    "Review this proposed Base USDC approval before I sign it and summarize "
    "the highest-risk points.\n\n"
    "This is a controlled test transaction. Do not broadcast or execute anything.\n\n"
    "Network: Base\n"
    "Token: USDC\n"
    "Token address: 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913\n"
    "Action: ERC-20 token approval\n"
    "Spender: 0x000000000000000000000000000000000000dEaD\n"
    "Allowance: unlimited / maximum allowance\n\n"
    "Explain what this approval would permit, identify the main security risks, "
    "and give an ALLOW, REVIEW, or AVOID recommendation with reasoning."
)


def _pipeline(text):
    spec = parse_job(text)
    contract = build_contract(spec, lessons=[])
    return spec, contract


def test_approval_review_routes_to_transaction_review():
    spec, contract = _pipeline(APPROVAL_REQUEST)
    assert transaction_review_request(APPROVAL_REQUEST) is True
    assert spec.job_type == "research"
    joined = " ".join(contract.deliverables).lower()
    assert "permission" in joined and "spender" in joined and "allowance" in joined
    assert "ALLOW, REVIEW, or AVOID" in contract.acceptance[-0] or any(
        "ground" in a.lower() for a in contract.acceptance)


def test_supplied_fields_are_treated_as_facts():
    _spec, contract = _pipeline(APPROVAL_REQUEST)
    grounding = " ".join(contract.acceptance).lower()
    for field in ("network", "token address", "spender", "allowance"):
        assert field in grounding
    assert "never mark a provided value as unknown" in grounding


def test_contract_deliverables_describe_the_review_not_a_market_sweep():
    _spec, contract = _pipeline(APPROVAL_REQUEST)
    lowered = [d.lower() for d in contract.deliverables]
    assert "names" not in lowered and "pricing" not in lowered
    assert "weaknesses" not in lowered
    assert any("verdict" in d for d in lowered)
    assert any("security risk" in d for d in lowered)


def test_acceptance_requires_grounding_in_supplied_fields():
    _spec, contract = _pipeline(APPROVAL_REQUEST)
    assert any(
        "ground the risk analysis" in a.lower() and "supplied transaction fields" in a.lower()
        for a in contract.acceptance
    )
    assert any("exact permission" in a.lower() for a in contract.acceptance)


def test_worker_payload_receives_corrected_clauses_and_raw_request():
    spec, contract = _pipeline(APPROVAL_REQUEST)
    payload = requirement_payload(contract, spec)
    text = str(payload["acceptance"]).lower()
    assert "never mark a provided value as unknown" in text
    assert payload["raw"] == APPROVAL_REQUEST
    assert payload["job_description"].startswith("Review this proposed Base USDC approval")
    for field in ("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "0x000000000000000000000000000000000000dEaD"):
        assert field in payload["job_description"] or field in payload["raw"]


def test_review_only_constraint_survives():
    spec, contract = _pipeline(APPROVAL_REQUEST)
    payload = requirement_payload(contract, spec)
    assert any(
        "do not broadcast, sign, execute, or mutate" in a.lower()
        for a in payload["acceptance"]
    )


def test_ordinary_research_classes_keep_existing_deliverables():
    wallet = parse_job("Research the top five AI wallet companies and compare their features.")
    assert "pricing" in wallet.deliverables or "products" in wallet.deliverables
    assert transaction_review_request("Research the top five AI wallet companies and compare their features.") is False
    dex = parse_job("Research the top five decentralized exchanges.")
    assert dex.deliverables[1:] == ["products", "pricing", "strengths", "weaknesses"]
    suppliers = parse_job("Find suppliers for packaging")
    assert suppliers.deliverables[0] == "supplier names"
    landscape = parse_job("Map the L2 landscape")
    assert "category map" in landscape.deliverables


def test_missing_transaction_artifact_validation_still_works():
    assert missing_review_artifact("Review this transaction for risks") == "transaction"
    assert missing_review_artifact(APPROVAL_REQUEST) is None


def test_detection_is_semantic_not_literal():
    assert transaction_review_request("Analyze this approval: spender 0xabc, unlimited allowance")
    assert transaction_review_request("audit the swap transaction before I sign")
    assert not transaction_review_request("Compare wallet products and their pricing")
    assert not transaction_review_request("Review the top five L2 sequencer teams")


def test_no_provider_or_job_literals_in_semantic_layer():
    source = Path("src/prior/job_spec.py").read_text(encoding="utf-8")
    for needle in ("77892", "COINGAZURA", "coingazura", "0x66ebcaf", "0xcc9d047"):
        assert needle not in source
