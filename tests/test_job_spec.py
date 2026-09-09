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


def test_hyphenated_standards_do_not_create_counts():
    from prior.job_spec import _extract_count
    for text in [
        "Action: ERC-20 token approval",
        "Review an ERC-20 approval",
        "Explain EIP-1559",
        "Review SHA-256 usage",
        "Analyze Base chain ID 8453",
        "Research crypto security in 2026",
        "version 2 of the protocol",
        "HTTP/2 performance",
    ]:
        assert _extract_count(text.lower()) is None, text


def test_genuine_cardinality_still_counts():
    from prior.job_spec import _extract_count
    assert _extract_count("research 5 wallets") == 5
    assert _extract_count("compare 3 exchanges") == 3
    assert _extract_count("list the top 10 protocols") == 10
    assert _extract_count("find five competitors") == 5
    assert _extract_count("best 5 dexes") == 5


def test_missing_review_artifact_detected():
    from prior.job_spec import missing_review_artifact
    assert missing_review_artifact("Review this Solidity contract for issues.") == "contract"
    assert missing_review_artifact(
        "Analyze this transaction 0x8c95120c327ccfcd5c003f1dab484d341f75160e"
        "8899aabbccddeeff00112233.") is None
    assert missing_review_artifact("Research the top five AI wallet companies.") is None
