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
    _extract_relational_evidence,
    _extract_grounded_strength,
    _extract_grounded_weakness,
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


def test_company_with_wallet_and_unrelated_ai_is_rejected():
    # 1. Company has wallet + unrelated AI feature (e.g. Opera or separate customer chatbot) -> REJECT
    ai_spec = parse_job("Research the top five AI wallet companies and compare their products, pricing, strengths, and weaknesses.")
    ai_facets = extract_facets(ai_spec)

    opera_text = "Opera Norway AS offers PC browsers, Web3 wallet and e-commerce products. Opera is noted for early adoption of technologies such as artificial intelligence (AI), cryptocurrency, and Web3. The company has 296 million users."
    valid, reason, _ = _validate_candidate_facets(
        "Opera",
        opera_text,
        "",
        "https://en.wikipedia.org/wiki/Opera_(company)",
        ai_facets,
    )
    assert not valid
    assert "Missing relational evidence" in reason

    support_ai_text = "Trust Wallet is a multi-chain non-custodial crypto wallet. Company also uses an AI chatbot for customer support inquiries."
    valid, reason, _ = _validate_candidate_facets(
        "Trust Wallet",
        support_ai_text,
        "",
        "https://trustwallet.com",
        ai_facets,
    )
    assert not valid
    assert "Missing relational evidence" in reason


def test_company_with_ai_and_unrelated_wallet_is_rejected():
    # 2. Company has AI + unrelated corporate crypto wallet -> REJECT
    ai_spec = parse_job("Research the top five AI wallet companies and compare their products, pricing, strengths, and weaknesses.")
    ai_facets = extract_facets(ai_spec)

    openai_text = "OpenAI develops advanced large language models including GPT-4. The organization maintains a corporate digital wallet to hold investment reserves."
    valid, reason, _ = _validate_candidate_facets(
        "OpenAI",
        openai_text,
        "",
        "https://openai.com",
        ai_facets,
    )
    assert not valid
    assert "Missing relational evidence" in reason


def test_ai_capability_explicitly_tied_to_wallet_is_accepted():
    # 3. AI capability explicitly tied to wallet/account/on-chain execution -> ACCEPT
    ai_spec = parse_job("Research the top five AI wallet companies and compare their products, pricing, strengths, and weaknesses.")
    ai_facets = extract_facets(ai_spec)

    skyfire_text = "Skyfire is an AI payment and autonomous agent wallet platform enabling AI agents to execute on-chain transactions."
    valid, reason, evidence = _validate_candidate_facets(
        "Skyfire",
        skyfire_text,
        "",
        "https://skyfire.xyz",
        ai_facets,
    )
    assert valid
    assert reason == "Valid"
    assert "ai" in evidence["qualifiers"]
    assert "Skyfire" in evidence["qualifiers"]["ai"]["evidence"] or "agent" in evidence["qualifiers"]["ai"]["evidence"]


def test_unsupported_strengths_and_weaknesses_are_not_invented():
    # 5. Unsupported strengths and weaknesses must return truthful unavailable messages, not corporate trivia or boilerplate
    bio_text = "Opera Norway AS is a multinational technology corporation headquartered in Oslo, Norway, with additional offices in Europe, China, and Africa. The company has 296 million monthly active users."
    strength = _extract_grounded_strength(bio_text, "Opera")
    weakness = _extract_grounded_weakness(bio_text, "Opera")

    assert strength == "Could not verify a specific strength from the retrieved sources."
    assert weakness == "Could not verify a specific weakness from the retrieved sources."
    assert "headquartered" not in strength
    assert "Subject to ecosystem integration requirements" not in weakness

    # Grounded capability -> extracted
    grounded_text = "Skyfire enables AI agents to execute autonomous on-chain micropayments with pre-configured spending limits. Requires developer integration with agent frameworks."
    extracted_strength = _extract_grounded_strength(grounded_text, "Skyfire")
    extracted_weakness = _extract_grounded_weakness(grounded_text, "Skyfire")

    assert "enables AI agents" in extracted_strength
    assert "Requires developer integration" in extracted_weakness


def test_compound_qualifier_relationship_works_on_unrelated_fixture_domain():
    # 7. Relational binding on unrelated fixture domains (e.g. privacy-first search engine, self-hosted database)
    text_privacy_search = "DuckDuckGo is a privacy-first search engine that does not track user search queries."
    ev = _extract_relational_evidence(text_privacy_search, "search_engine", "privacy")
    assert ev is not None
    assert "privacy-first search engine" in ev


def test_zero_qualifying_results_is_allowed():
    # 4. Zero results is valid and produces truthful notes
    spec = parse_job("Research 5 non-existent hyper-quantum teleportation widgets.")
    contract = build_contract(spec, [])
    report = run_research(spec, contract)

    val = report["value"]
    assert isinstance(val["findings"], list)
    assert len(val["findings"]) == 0
    assert "0 qualifying entities could be verified from the available sources." in val["notes"]
    assert "No public sources answered this query with verified qualification." in val["notes"]


def test_pricing_is_truthful_and_not_defaulted():
    # If pricing is in text, extract it
    assert _extract_truthful_pricing("Plans start at $29/mo with 14-day free trial.", "") == "Plans start at $29/mo with 14-day free trial"
    assert _extract_truthful_pricing("Offers a 100% free community edition.", "") == "100% free"

    # If pricing is absent, DO NOT invent or default to generic text
    fallback = _extract_truthful_pricing("Multi-chain wallet supporting ERC-4337 smart accounts.", "")
    assert fallback == "Not publicly disclosed in the retrieved source."
    assert "standard network or on-chain transaction fees apply" not in fallback


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
