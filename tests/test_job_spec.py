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


def test_imperative_research_still_supported():
    spec = parse_job("Research the top five AI wallet companies and compare their features.")
    assert spec.job_type == "research"
    assert spec.refusal_reason is None


def test_question_shaped_research_reaches_selection():
    for text in [
        "What are the main differences between current hardware wallet security models?",
        "Which hardware wallet security models are used today and what evidence supports them?",
        "How does Base chain settlement work? Summarize the key steps.",
    ]:
        spec = parse_job(text)
        assert spec.job_type == "research", text
        assert spec.refusal_reason is None


def test_non_research_questions_stay_unsupported():
    for text in [
        "Write code to deploy a contract",
        "Send an email to the team about lunch",
        "Generate an image of a sunset",
    ]:
        spec = parse_job(text)
        assert spec.job_type == "unsupported", text
        assert spec.refusal_reason
