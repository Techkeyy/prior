import pytest
from prior.domain import Contract, JobSpec
from prior.job_spec import parse_job
from prior.contract import build_contract
from prior.research import run_research, _is_semantically_relevant, search_queries


def test_subject_extraction_strips_comparison_conjunction():
    raw = "Research the top five AI wallet companies and compare their products, pricing, strengths, and weaknesses."
    spec = parse_job(raw)
    assert spec.subject == "AI wallet companies"
    assert spec.count == 5
    assert spec.domain == "ai wallets"


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


def test_ai_wallet_research_returns_relevant_contract_deliverables():
    raw = "Research the top five AI wallet companies and compare their products, pricing, strengths, and weaknesses."
    spec = parse_job(raw)
    contract = build_contract(spec, [])
    report = run_research(spec, contract)

    value = report["value"]
    findings = value["findings"]
    assert len(findings) >= 1

    unrelated_blacklist = ["crayon shin-chan", "ai weiwei", "ai otsuka", "episodes", "discography"]
    for finding in findings:
        name_lower = finding["name"].lower()
        summary_lower = finding["summary"].lower()
        for bad in unrelated_blacklist:
            assert bad not in name_lower, f"Unrelated entity found: {finding['name']}"
            assert bad not in summary_lower, f"Unrelated entity in summary: {finding['summary']}"

    deliverables = value["deliverables"]
    assert "names" in deliverables
    assert "products" in deliverables
    assert "pricing" in deliverables
    assert "strengths" in deliverables
    assert "weaknesses" in deliverables

    # Verify every finding has structured comparison fields
    for finding in findings:
        assert finding.get("pricing")
        assert finding.get("strengths")
        assert finding.get("weaknesses")
        assert len(finding.get("sources", [])) > 0


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
