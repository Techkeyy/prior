import pytest
from pathlib import Path
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
    _extract_supported_platforms,
    validate_deliverable_against_contract,
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
    assert is_publisher_or_agency("Password manager")
    assert is_publisher_or_agency("Password managers")
    assert is_publisher_or_agency("Password management")

    # Genuine companies and products must NOT be rejected
    assert not is_publisher_or_agency("Trust Wallet")
    assert not is_publisher_or_agency("Electrum")
    assert not is_publisher_or_agency("Safe")
    assert not is_publisher_or_agency("World ID")
    assert not is_publisher_or_agency("ENS")
    assert not is_publisher_or_agency("Datadog")
    assert not is_publisher_or_agency("LaunchDarkly")
    assert not is_publisher_or_agency("Bitwarden")
    assert not is_publisher_or_agency("1Password")


def test_explicit_comparison_fields_survive_parsing_and_contract():
    # 1 & 2. Explicit arbitrary comparison fields survive parsing and contract generation
    raw = "Research three password managers and compare their pricing, supported platforms, strengths, and weaknesses."
    spec = parse_job(raw)
    assert spec.count == 3
    assert spec.subject == "password managers"
    assert "supported platforms" in spec.deliverables
    assert "pricing" in spec.deliverables
    assert "strengths" in spec.deliverables
    assert "weaknesses" in spec.deliverables
    assert "products" not in spec.deliverables  # Was not replaced by generic "products"

    contract = build_contract(spec, [])
    assert "supported platforms" in contract.deliverables
    assert "pricing" in contract.deliverables

    # Arbitrary comparison request
    raw2 = "compare deployment options, API support, and pricing for 3 observability platforms"
    spec2 = parse_job(raw2)
    assert "deployment options" in spec2.deliverables
    assert "api support" in spec2.deliverables
    assert "pricing" in spec2.deliverables


def test_generic_category_concept_cannot_count_as_requested_entity():
    # 3. Generic concept title must be rejected from findings
    spec = parse_job("Research three password managers and compare their pricing, supported platforms, strengths, and weaknesses.")
    facets = extract_facets(spec)

    valid, reason, _ = _validate_candidate_facets(
        "Password manager",
        "A password manager is a computer program that allows users to store passwords.",
        "",
        "https://en.wikipedia.org/wiki/Password_manager",
        facets,
    )
    assert not valid
    assert any(w in reason.lower() for w in ("generic", "concept", "publisher", "category"))


def test_final_findings_preserve_every_requested_comparison_field():
    # 4 & 5. Final findings preserve all requested fields with grounded values or truthful unavailable markers
    spec = parse_job("Research three password managers and compare their pricing, supported platforms, strengths, and weaknesses.")
    contract = build_contract(spec, [])
    report = run_research(spec, contract)

    value = report["value"]
    findings = value["findings"]
    assert len(findings) <= 3

    for f in findings:
        assert f["name"] != "Password manager"
        assert not is_publisher_or_agency(f["name"])
        # All requested comparison fields must exist on the finding object
        assert "pricing" in f
        assert "supported_platforms" in f or "supported platforms" in f
        assert "strengths" in f
        assert "weaknesses" in f
        assert len(f.get("sources", [])) > 0

    # Deliverables map must also contain the requested comparison fields
    deliv = value["deliverables"]
    assert "supported platforms" in deliv
    assert "pricing" in deliv
    assert "strengths" in deliv
    assert "weaknesses" in deliv


def test_contract_completeness_validator():
    # 6. Validator rejects missing deliverable fields or generic concept entities
    spec = parse_job("Research three password managers and compare their pricing, supported platforms, strengths, and weaknesses.")
    contract = build_contract(spec, [])

    # Bad deliverable with generic concept entity
    bad_val = {
        "findings": [{"name": "Password manager", "pricing": "Free"}],
        "deliverables": {"requested": contract.deliverables, "supported platforms": ["Web"]},
    }
    is_valid, err = validate_deliverable_against_contract(contract, bad_val)
    assert not is_valid
    assert "generic category concept" in err

    # Bad deliverable missing requested field
    bad_val2 = {
        "findings": [{"name": "Bitwarden", "pricing": "Free"}],
        "deliverables": {"requested": contract.deliverables},  # Missing "supported platforms"
    }
    is_valid, err = validate_deliverable_against_contract(contract, bad_val2)
    assert not is_valid
    assert "Missing requested deliverable field" in err


def test_frontend_header_and_contract_status_consistency():
    # 7 & 8. Frontend code contains YOUR WORKSPACE and correct FULFILLED contract status
    app_js_path = Path(__file__).resolve().parent.parent / "src" / "prior" / "static" / "app.js"
    app_js_text = app_js_path.read_text(encoding="utf-8")

    assert "OPERATOR WORKSPACE" not in app_js_text
    assert "YOUR WORKSPACE" in app_js_text
    assert 'if (job.status === "delivered") return "FULFILLED";' in app_js_text


def test_company_with_wallet_and_unrelated_ai_is_rejected():
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


def test_unsupported_strengths_and_weaknesses_are_not_invented():
    bio_text = "Opera Norway AS is a multinational technology corporation headquartered in Oslo, Norway, with additional offices in Europe, China, and Africa. The company has 296 million monthly active users."
    strength = _extract_grounded_strength(bio_text, "Opera")
    weakness = _extract_grounded_weakness(bio_text, "Opera")

    assert strength == "Could not verify a specific strength from the retrieved sources."
    assert weakness == "Could not verify a specific weakness from the retrieved sources."
    assert "headquartered" not in strength


def test_pricing_is_truthful_and_not_defaulted():
    assert _extract_truthful_pricing("Plans start at $29/mo with 14-day free trial.", "") == "Plans start at $29/mo with 14-day free trial"
    assert _extract_truthful_pricing("Offers a 100% free community edition.", "") == "100% free"

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


def test_authoritative_resolution_and_field_citations():
    # 1. Discovery from Wikipedia, pricing and platforms from official site
    # 2. Official platform page beats incomplete summary
    # 3. Multiple fields use distinct source pages
    # 4. Unofficial/community ports distinguished from official support
    from prior.research import (
        resolve_official_domain,
        extract_first_party_pricing,
        extract_first_party_platforms,
        extract_first_party_strength,
        extract_first_party_weakness,
    )

    # Test official-domain resolver
    keeper_dom = resolve_official_domain("Keeper", "Keeper_(password_manager)")
    assert keeper_dom is not None
    assert "keepersecurity.com" in keeper_dom["domain"]

    lastpass_dom = resolve_official_domain("LastPass", "LastPass")
    assert lastpass_dom is not None
    assert "lastpass.com" in lastpass_dom["domain"]

    keepass_dom = resolve_official_domain("KeePass", "KeePass")
    assert keepass_dom is not None
    assert "keepass.info" in keepass_dom["domain"]

    # 4. Unofficial/community platform distinguished
    kp_plat, kp_plat_src, _ = extract_first_party_platforms("KeePass", "keepass.info", "https://keepass.info", "KeePass on Mono and Wine. Contributed ports for Android and iOS.")
    assert "Official: Windows" in kp_plat
    assert "Mono/Wine" in kp_plat
    assert "Contributed/Unofficial" in kp_plat or "Ports" in kp_plat

    # 5. Pricing quality: Free & open source vs tiered structure
    kp_price, kp_p_src, _ = extract_first_party_pricing("KeePass", "keepass.info", "https://keepass.info", "free and open source")
    assert "Free and open-source" in kp_price
    assert len(kp_p_src) > 0

    # 6. Irrelevant acquisition/history is not accepted as weakness
    acq_text = "In October 2015 when GoTo acquired LastPass, founder blog was filled with user comments. Keeper was bundled with Windows 10."
    assert _extract_grounded_weakness(acq_text, "LastPass") == "Could not verify a specific weakness from the retrieved sources."

    # 7. Official-domain resolver rejects review/listicle/article domains
    from prior.research import NON_OFFICIAL_DOMAINS
    for d in ["pcmag.com", "techradar.com", "g2.com", "capterra.com", "tomsguide.com", "wikipedia.org"]:
        assert d in NON_OFFICIAL_DOMAINS

    # 8 & 9. Truly unavailable data remains truthful
    unavail_p, unavail_src, _ = extract_first_party_pricing("UnknownTool", "", "", "")
    assert unavail_p == "Tiered personal, family, and business subscription plans available; numeric prices are dynamically rendered on official site." or unavail_p == "Not publicly disclosed in the retrieved source."


def test_field_grounding_and_strict_entailment():
    from prior.research import (
        extract_first_party_pricing,
        extract_first_party_platforms,
        extract_first_party_strength,
        extract_first_party_weakness,
        _build_finding_object,
        extract_facets,
    )

    # 1. Current pricing page beats historical pricing blog
    # 2. Stale numeric price is rejected
    # 3. Unrelated number on same page cannot become pricing
    # 4. User-count value cannot become price
    # 5. Values from Entity A cannot leak into Entity B
    # 6. Exact field source must entail exact returned value
    # 7. Dynamic/unextractable price becomes truthful unavailable state
    # 8. Current source without numeric price does not trigger historical fallback
    # 9. Separate products preserve distinct exact counts
    # 10. Field-specific evidence remains isolated

    # Test Keeper exact count (5 private vaults) vs LastPass exact count (6 user accounts)
    k_price, k_src, k_ev = extract_first_party_pricing("Keeper", "keepersecurity.com", "https://keepersecurity.com", "")
    assert "Family (5 private vaults)" in k_price
    assert "6 user accounts" not in k_price
    assert len(k_src) > 0
    assert "5 private vaults" in k_ev

    lp_price, lp_src, lp_ev = extract_first_party_pricing("LastPass", "lastpass.com", "https://lastpass.com", "")
    assert "Families (6 user accounts)" in lp_price
    assert "5 private vaults" not in lp_price
    assert len(lp_src) > 0
    assert "6 user accounts" in lp_ev

    # Test unextractable dynamic pricing returns truthful state and does not scrape loose unrelated digits
    assert "$110" not in lp_price
    assert "$48" not in lp_price
    assert "$60" not in k_price

    # Test distinct platform sources and isolation
    k_plat, k_p_src, k_p_ev = extract_first_party_platforms("Keeper", "keepersecurity.com", "https://keepersecurity.com", "")
    assert "Windows" in k_plat
    assert "macOS" in k_plat
    assert len(k_p_src) > 0

    # Test isolation: finding object contains isolated field evidences
    spec = parse_job("Research three password managers and compare their pricing, supported platforms, strengths, and weaknesses.")
    contract = build_contract(spec, [])
    facets = extract_facets(spec)
    finding = _build_finding_object("LastPass", facets, spec, contract, "", "", "", "https://en.wikipedia.org/wiki/LastPass", "Wikipedia", {}, "LastPass")

    assert finding["pricing_evidence"] != ""
    assert finding["platform_evidence"] != ""
    assert finding["strength_evidence"] != ""
    assert finding["weakness_evidence"] != ""
    assert finding["pricing_sources"] != []
    assert finding["supported_platform_sources"] != []
    assert finding["strength_sources"] != []
    assert finding["weakness_sources"] != []
