import pytest
from prior import research
from prior.domain import Contract, JobSpec
from prior.job_spec import parse_job
from prior.contract import build_contract
from prior.research import run_research, _is_semantically_relevant, is_publisher_or_agency, search_queries


def test_zero_hardcoded_domain_entity_registries():
    # Enforce strictly that no hardcoded answer dictionaries or domain registries exist
    assert not hasattr(research, "DOMAIN_ENTITIES")
    assert not hasattr(research, "KNOWN_ENTITIES")
    assert not hasattr(research, "DOMAIN_ANSWERS")


def test_subject_extraction_strips_comparison_conjunction():
    raw = "Research the top five AI wallet companies and compare their products, pricing, strengths, and weaknesses."
    spec = parse_job(raw)
    assert spec.subject == "AI wallet companies"
    assert spec.count == 5
    assert spec.domain == "ai wallets"


def test_publisher_and_agency_rejection():
    # Publisher titles/articles must NOT become entities
    assert is_publisher_or_agency("CoinGape Agentic Wallets")
    assert is_publisher_or_agency("CoinCreate AI Wallets")
    assert is_publisher_or_agency("Antier AI Wallet Development")
    assert is_publisher_or_agency("SoluLab AI Wallets")
    assert is_publisher_or_agency("BlockchainX AI Wallets")
    assert is_publisher_or_agency("Forbes")
    assert is_publisher_or_agency("LinkedIn")
    assert is_publisher_or_agency("Medium")

    # Generic concepts must NOT become entities
    assert is_publisher_or_agency("Cryptocurrency")
    assert is_publisher_or_agency("Artificial Intelligence")
    assert is_publisher_or_agency("Smart Contract")
    assert is_publisher_or_agency("Digital Wallet")

    # Genuine companies and products must NOT be rejected
    assert not is_publisher_or_agency("Trust Wallet")
    assert not is_publisher_or_agency("Dawn Wallet")
    assert not is_publisher_or_agency("Safe")
    assert not is_publisher_or_agency("World ID")
    assert not is_publisher_or_agency("ENS")
    assert not is_publisher_or_agency("Datadog")
    assert not is_publisher_or_agency("LaunchDarkly")


def test_semantic_relevance_discards_unrelated_media_and_artists():
    spec = parse_job("Research the top five AI wallet companies and compare their products, pricing, strengths, and weaknesses.")
    
    # TV episode list must be rejected
    assert not _is_semantically_relevant(
        "List of Crayon Shin-chan episodes (1992-2001)",
        "List of episodes of the Japanese anime television series Crayon Shin-chan.",
        spec,
    )
    
    # Unrelated artist must be rejected
    assert not _is_semantically_relevant(
        "Ai Weiwei",
        "Ai Weiwei is a Chinese contemporary artist and documentarian.",
        spec,
    )
    
    # Unrelated singer must be rejected
    assert not _is_semantically_relevant(
        "Ai Otsuka",
        "Ai Otsuka is a Japanese singer-songwriter and pianist.",
        spec,
    )
    
    # Genuine AI wallet hits must be accepted
    assert _is_semantically_relevant(
        "Trust Wallet",
        "Trust Wallet is a cryptocurrency smart contract self-custody wallet with automated security scanner.",
        spec,
    )
    assert _is_semantically_relevant(
        "Dawn AI Wallet",
        "Dawn is an AI-powered smart contract self-custody wallet with automated execution.",
        spec,
    )


def test_ai_wallet_research_returns_real_operating_entities_not_publishers():
    raw = "Research the top five AI wallet companies and compare their products, pricing, strengths, and weaknesses."
    spec = parse_job(raw)
    contract = build_contract(spec, [])
    report = run_research(spec, contract)

    value = report["value"]
    findings = value["findings"]
    assert len(findings) >= 1

    publisher_blacklist = [
        "coingape", "coincreate", "antier", "solulab", "blockchainx",
        "forbes", "linkedin", "medium", "development companies", "crayon shin-chan"
    ]
    for finding in findings:
        name_lower = finding["name"].lower()
        for bad in publisher_blacklist:
            assert bad not in name_lower, f"Publisher or agency returned as entity: {finding['name']}"
        
        # Verify entity type and comparison fields
        assert finding.get("type") in ("Company / Product", "Company / Protocol", "Company / Infrastructure")
        assert finding.get("pricing")
        assert finding.get("strengths")
        assert finding.get("weaknesses")
        assert len(finding.get("sources", [])) > 0
        assert finding["sources"][0]["url"].startswith("http")

    deliverables = value["deliverables"]
    assert "names" in deliverables
    assert len(deliverables["names"]) >= 1


def test_decentralized_identity_research_generalization():
    raw = "Research 3 decentralized identity protocols on Base and summarize key capabilities"
    spec = parse_job(raw)
    assert "identity" in spec.subject.lower()
    contract = build_contract(spec, [])
    report = run_research(spec, contract)

    value = report["value"]
    findings = value["findings"]
    assert len(findings) >= 1
    for finding in findings:
        assert finding.get("name")
        assert finding.get("summary")
        assert len(finding.get("sources", [])) > 0
        assert not is_publisher_or_agency(finding["name"])


def test_unseen_fixture_observability_generalization():
    raw = "Research 3 API observability platforms and compare features"
    spec = parse_job(raw)
    contract = build_contract(spec, [])
    report = run_research(spec, contract)

    value = report["value"]
    findings = value["findings"]
    assert len(findings) >= 1
    for finding in findings:
        assert finding.get("name")
        assert finding.get("summary")
        assert len(finding.get("sources", [])) > 0
        assert not is_publisher_or_agency(finding["name"])


def test_unseen_fixture_feature_flags_generalization():
    raw = "Research 3 open-source feature flag tools"
    spec = parse_job(raw)
    contract = build_contract(spec, [])
    report = run_research(spec, contract)

    value = report["value"]
    findings = value["findings"]
    assert len(findings) >= 1
    for finding in findings:
        assert finding.get("name")
        assert finding.get("summary")
        assert len(finding.get("sources", [])) > 0
        assert not is_publisher_or_agency(finding["name"])
