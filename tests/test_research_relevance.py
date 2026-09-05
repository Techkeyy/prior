import pytest
from prior import research
from prior.domain import Contract, JobSpec
from prior.job_spec import parse_job
from prior.contract import build_contract
from prior.research import (
    run_research,
    _is_semantically_relevant,
    is_publisher_or_agency,
    search_queries,
    extract_facets,
    _validate_candidate_facets,
    _extract_truthful_pricing,
)


def test_zero_hardcoded_domain_entity_registries():
    # Enforce strictly that no hardcoded answer dictionaries or domain registries exist
    assert not hasattr(research, "DOMAIN_ENTITIES")
    assert not hasattr(research, "KNOWN_ENTITIES")
    assert not hasattr(research, "DOMAIN_ANSWERS")


def test_subject_extraction_and_facet_derivation():
    raw = "Research the top five AI wallet companies and compare their products, pricing, strengths, and weaknesses."
    spec = parse_job(raw)
    assert spec.subject == "AI wallet companies"
    assert spec.count == 5
    assert spec.domain == "ai wallets"

    facets = extract_facets(spec)
    assert "ai" in facets.mandatory_qualifiers
    assert facets.domain == "wallet"
    assert facets.entity_type == "Company / Product"
    assert facets.target_count == 5


def test_publisher_and_agency_rejection():
    # Publisher titles/articles/agencies must NOT become entities
    assert is_publisher_or_agency("CoinGape Agentic Wallets")
    assert is_publisher_or_agency("CoinCreate AI Wallets")
    assert is_publisher_or_agency("Antier AI Wallet Development")
    assert is_publisher_or_agency("SoluLab AI Wallets")
    assert is_publisher_or_agency("BlockchainX AI Wallets")
    assert is_publisher_or_agency("Forbes")
    assert is_publisher_or_agency("LinkedIn")
    assert is_publisher_or_agency("Medium")
    assert is_publisher_or_agency("Cloud Native Computing Foundation")
    assert is_publisher_or_agency("Linux Foundation")

    # Generic concepts / 2-letter tokens must NOT become entities
    assert is_publisher_or_agency("AI")
    assert is_publisher_or_agency("LLM")
    assert is_publisher_or_agency("API")
    assert is_publisher_or_agency("Cryptocurrency")
    assert is_publisher_or_agency("Artificial Intelligence")
    assert is_publisher_or_agency("Smart Contract")
    assert is_publisher_or_agency("Digital Wallet")

    # Genuine companies and products must NOT be rejected
    assert not is_publisher_or_agency("Trust Wallet")
    assert not is_publisher_or_agency("Electrum")
    assert not is_publisher_or_agency("Safe")
    assert not is_publisher_or_agency("World ID")
    assert not is_publisher_or_agency("ENS")
    assert not is_publisher_or_agency("Datadog")
    assert not is_publisher_or_agency("LaunchDarkly")


def test_mandatory_qualifier_validation_rejects_unqualified_candidates():
    # 1. AI Wallet query: candidate with wallet but NO AI must be rejected
    ai_spec = parse_job("Research the top five AI wallet companies and compare their products, pricing, strengths, and weaknesses.")
    ai_facets = extract_facets(ai_spec)

    # Trust Wallet without AI claims in text -> FAIL for AI wallet request
    valid, reason = _validate_candidate_facets(
        "Trust Wallet",
        "Trust Wallet is a multi-chain non-custodial crypto wallet.",
        "",
        "https://en.wikipedia.org/wiki/Trust_Wallet",
        ai_facets,
    )
    assert not valid
    assert "AI" in reason

    # Generic digital wallet (OPay, Google Wallet) -> FAIL for AI wallet request
    valid, reason = _validate_candidate_facets(
        "Google Wallet",
        "Google Wallet is a digital wallet platform developed by Google.",
        "",
        "https://en.wikipedia.org/wiki/Google_Wallet",
        ai_facets,
    )
    assert not valid

    # Candidate WITH AI agentic wallet capability -> PASS
    valid, reason = _validate_candidate_facets(
        "Skyfire",
        "Skyfire is an AI payment and autonomous agent wallet infrastructure platform enabling AI agents to execute on-chain transactions.",
        "",
        "https://skyfire.xyz",
        ai_facets,
    )
    assert valid

    # 2. Open-source feature flag query: proprietary tool without open-source evidence must be rejected
    ff_spec = parse_job("Research 3 open-source feature flag tools.")
    ff_facets = extract_facets(ff_spec)

    # LaunchDarkly without open source evidence -> FAIL
    valid, reason = _validate_candidate_facets(
        "LaunchDarkly",
        "LaunchDarkly is a proprietary commercial SaaS feature management platform.",
        "",
        "https://launchdarkly.com",
        ff_facets,
    )
    assert not valid
    assert "open-source" in reason.lower()

    # Unleash / Flagsmith with open source evidence -> PASS
    valid, reason = _validate_candidate_facets(
        "Unleash",
        "Unleash is an open-source feature flag management tool available on GitHub with self-hosted and cloud options.",
        "",
        "https://github.com/Unleash/unleash",
        ff_facets,
    )
    assert valid

    # 3. Self-hosted observability query: SaaS only must be rejected
    obs_spec = parse_job("Research 3 self-hosted API observability platforms.")
    obs_facets = extract_facets(obs_spec)

    # Datadog SaaS only -> FAIL
    valid, reason = _validate_candidate_facets(
        "Datadog",
        "Datadog is a cloud-hosted SaaS monitoring and security platform for cloud applications.",
        "",
        "https://datadoghq.com",
        obs_facets,
    )
    assert not valid
    assert "self-hosted" in reason.lower()

    # SigNoz self-hosted -> PASS
    valid, reason = _validate_candidate_facets(
        "SigNoz",
        "SigNoz is a self-hosted open-source APM and observability platform you can deploy with Docker or Kubernetes.",
        "",
        "https://signoz.io",
        obs_facets,
    )
    assert valid


def test_pricing_is_truthful_and_not_defaulted():
    # If pricing is in text, extract it
    assert _extract_truthful_pricing("Plans start at $29/mo with 14-day free trial.", "") == "Plans start at $29/mo with 14-day free trial"
    assert _extract_truthful_pricing("Offers a 100% free community edition.", "") == "100% free"

    # If pricing is absent, DO NOT invent or default to generic text
    fallback = _extract_truthful_pricing("Multi-chain wallet supporting ERC-4337 smart accounts.", "")
    assert fallback == "Not publicly disclosed in the retrieved source."
    assert "standard network or on-chain transaction fees apply" not in fallback


def test_ai_wallet_research_returns_only_qualified_entities_and_no_forced_padding():
    raw = "Research the top five AI wallet companies and compare their products, pricing, strengths, and weaknesses."
    spec = parse_job(raw)
    contract = build_contract(spec, [])
    report = run_research(spec, contract)

    value = report["value"]
    findings = value["findings"]
    
    # We do NOT force 5 results; we accept whatever genuinely qualified
    assert len(findings) <= 5

    # Check that every single returned entity has verified sources and non-invented pricing
    for finding in findings:
        assert not is_publisher_or_agency(finding["name"])
        assert finding["type"] == "Company / Product"
        assert "standard network or on-chain transaction fees apply" not in finding.get("pricing", "")
        assert len(finding.get("sources", [])) > 0


def test_open_source_feature_flags_generalization():
    raw = "Research 3 open-source feature flag tools."
    spec = parse_job(raw)
    contract = build_contract(spec, [])
    report = run_research(spec, contract)

    value = report["value"]
    findings = value["findings"]
    assert len(findings) <= 3
    for finding in findings:
        assert not is_publisher_or_agency(finding["name"])
        assert finding["type"] == "Tool / Product"


def test_self_hosted_observability_generalization():
    raw = "Research 3 self-hosted API observability platforms."
    spec = parse_job(raw)
    contract = build_contract(spec, [])
    report = run_research(spec, contract)

    value = report["value"]
    findings = value["findings"]
    assert len(findings) <= 3
    for finding in findings:
        assert not is_publisher_or_agency(finding["name"])
        assert finding["type"] == "Platform / Product"


def test_non_custodial_crypto_wallets_generalization():
    raw = "Research 3 non-custodial crypto wallets."
    spec = parse_job(raw)
    contract = build_contract(spec, [])
    report = run_research(spec, contract)

    value = report["value"]
    findings = value["findings"]
    assert len(findings) <= 3
    for finding in findings:
        assert not is_publisher_or_agency(finding["name"])
        assert finding["type"] == "Company / Product"
