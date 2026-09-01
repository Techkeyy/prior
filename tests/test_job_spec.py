from prior.job_spec import parse_job
from prior.research import search_queries


def test_wallet_research_is_supported():
    spec = parse_job("Research the top five AI wallet companies.")
    assert spec.job_type == "research"
    assert spec.count == 5
    assert spec.domain == "ai wallets"
    assert "names" in spec.deliverables[0] or spec.deliverables


def test_dex_research_differs_from_wallets():
    wallets = parse_job("Research the top five AI wallet companies.")
    dex = parse_job("Research the top five decentralized exchanges.")
    assert wallets.domain != dex.domain
    assert "exchanges" in dex.domain or "decentralized" in dex.domain


def test_code_job_is_refused():
    spec = parse_job("Write code to deploy a contract")
    assert spec.job_type == "unsupported"
    assert spec.refusal_reason
    assert "research" in spec.refusal_reason.lower()


def test_empty_job_is_refused():
    spec = parse_job("   ")
    assert spec.job_type == "unsupported"


def test_research_queries_use_subject_not_only_full_sentence():
    spec = parse_job("Research the top five AI wallet companies.")
    queries = search_queries(spec)
    assert spec.subject in queries
    assert spec.domain in queries
