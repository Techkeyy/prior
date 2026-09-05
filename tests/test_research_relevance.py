import pytest
from prior.domain import Contract, JobSpec
from prior.job_spec import parse_job
from prior.contract import build_contract
from prior.research import run_research, _is_semantically_relevant, _is_publisher_or_agency, search_queries


def test_subject_extraction_strips_comparison_conjunction():
    raw = "Research the top five AI wallet companies and compare their products, pricing, strengths, and weaknesses."
    spec = parse_job(raw)
    assert spec.subject == "AI wallet companies"
    assert spec.count == 5
    assert spec.domain == "ai wallets"


def test_publisher_and_agency_rejection():
    # Publisher titles/articles must NOT become entities
    assert _is_publisher_or_agency("CoinGape Agentic Wallets", "Best AI Crypto Wallets", "We reviewed 8 wallets")
    assert _is_publisher_or_agency("CoinCreate AI Wallets", "Best AI Crypto Wallets 2025", "Top 10 smart picks")
    assert _is_publisher_or_agency("Antier AI Wallet Development", "Top AI Crypto Wallet Development Companies in 2026 for Serious Businesses", "Development partners")
    assert _is_publisher_or_agency("SoluLab AI Wallets", "Top AI Crypto Wallet Development Companies in 2026", "Development services")
    assert _is_publisher_or_agency("BlockchainX AI Wallets", "Top 10 AI Crypto Wallet Development Companies in 2026", "Development partners")

    # Genuine companies and products must NOT be rejected
    assert not _is_publisher_or_agency("Trust Wallet", "Trust Wallet", "Self-custody multi-chain wallet")
    assert not _is_publisher_or_agency("Dawn Wallet", "Dawn Wallet", "AI-native smart contract wallet")
    assert not _is_publisher_or_agency("Safe (Safe{Core} AI)", "Safe", "Smart account infrastructure")
    assert not _is_publisher_or_agency("World ID (Worldcoin)", "World ID", "Proof of humanity protocol")
    assert not _is_publisher_or_agency("Ethereum Name Service (ENS)", "ENS", "Naming standard")


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
        "Best AI Crypto Wallets: Smart and Agentic Wallets Reviewed",
        "We analyzed AI-powered smart crypto wallets with automated transaction security and intent routing.",
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
    assert len(findings) == 5

    # Every entity must be a real company/product, NOT a publisher or development agency
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
    assert len(deliverables["names"]) == 5
    assert "Trust Wallet" in deliverables["names"]
    assert "Dawn Wallet" in deliverables["names"]
    assert "Safe (Safe{Core} AI)" in deliverables["names"]


def test_decentralized_identity_research_generalization():
    raw = "Research 3 decentralized identity protocols on Base and summarize key capabilities"
    spec = parse_job(raw)
    assert "identity" in spec.subject.lower()
    contract = build_contract(spec, [])
    report = run_research(spec, contract)

    value = report["value"]
    findings = value["findings"]
    assert len(findings) == 3
    for finding in findings:
        assert finding.get("name")
        assert finding.get("summary")
        assert len(finding.get("sources", [])) > 0
        assert not _is_publisher_or_agency(finding["name"], "", "")
