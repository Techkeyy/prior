"""Generalized category-relevance and entity<->domain identity regression tests.

Issue 1: unknown-category validation must prove CATEGORY MEMBERSHIP via
explicit relational evidence (candidate + requested category terms), not mere
candidate-name mention. No category is hardcoded anywhere.

Issue 2: official-domain acceptance must rest on positive entity<->domain
evidence (exact-page provenance, result identity mention + host similarity or
org relationship) — never one-token coincidence, never loose substrings.

All tests are offline (network helpers mocked).
"""

from unittest.mock import patch

from prior.job_spec import parse_job
from prior import research
from prior.research import (
    _category_terms,
    _extract_category_relation,
    _host_similarity_score,
    _validate_candidate_facets,
    extract_facets,
    resolve_official_domain,
)

CLOUD_RAW = (
    "Research three cloud storage services and compare their pricing, "
    "supported platforms, strengths, and weaknesses."
)
VC_RAW = (
    "Research three video conferencing platforms and compare their pricing "
    "and features."
)


def _cloud_facets():
    return extract_facets(parse_job(CLOUD_RAW))


def _vc_facets():
    return extract_facets(parse_job(VC_RAW))


# ---------------- Issue 1: category relevance ----------------

def test_no_hardcoded_category_registries():
    for attr in (
        "CLOUD_KEYWORDS",
        "CLOUD_TERMS",
        "STORAGE_KEYWORDS",
        "VIDEO_KEYWORDS",
        "CATEGORY_KEYWORDS",
        "CATEGORY_TERMS",
        "DOMAIN_KEYWORDS",
    ):
        assert not hasattr(research, attr), attr


def test_category_terms_derive_from_request():
    terms = _category_terms(_cloud_facets())
    assert "cloud" in terms
    assert "storage" in terms
    # Filler words must not become membership terms.
    assert "services" not in terms

    vc_terms = _category_terms(_vc_facets())
    assert "video" in vc_terms
    assert "conferencing" in vc_terms


def test_name_mention_alone_is_not_enough():
    facets = _cloud_facets()
    ok, reason, _ = _validate_candidate_facets(
        "Acme",
        "Acme is a software company headquartered in Oslo.",
        "Acme provides business software to enterprise customers.",
        "https://acme.example.com",
        facets,
    )
    assert not ok
    assert "relational" in reason.lower() or "category" in reason.lower()


def test_unrelated_software_company_rejected_for_cloud_request():
    facets = _cloud_facets()
    ok, _, _ = _validate_candidate_facets(
        "Initech",
        "Initech is a software company selling accounting tools.",
        "Initech serves small businesses with invoicing software.",
        "https://initech.example.com",
        facets,
    )
    assert not ok


def test_broad_parent_platform_rejected_without_service_evidence():
    """'Google Cloud Platform ... cloud computing platform' shares the word
    'cloud' but nothing establishes it as a cloud STORAGE service."""
    facets = _cloud_facets()
    ok, reason, _ = _validate_candidate_facets(
        "Google Cloud Platform",
        "Google Cloud Platform is a cloud computing platform by Google.",
        "Suite of cloud computing services running on Google infrastructure.",
        "https://cloud.google.com",
        facets,
    )
    assert not ok
    assert "relational" in reason.lower() or "category" in reason.lower()


def test_valid_unfamiliar_candidate_passes_with_explicit_connection():
    facets = _cloud_facets()
    ok, reason, evidence = _validate_candidate_facets(
        "Dropbox",
        "Dropbox is a file hosting service that offers cloud storage.",
        "Dropbox provides cloud storage and file synchronization for teams.",
        "https://dropbox.com",
        facets,
    )
    assert ok, reason
    rel = evidence["product_domain"]["snippet"]
    assert "dropbox" in rel.lower()
    assert "cloud" in rel.lower()


def test_second_unknown_category_enforces_membership():
    """Same generalized rule on a second previously-unknown category."""
    facets = _vc_facets()
    assert facets.domain != "password_manager"

    ok, _, _ = _validate_candidate_facets(
        "Acme",
        "Acme is a software company headquartered in Oslo.",
        "Acme provides business software to enterprise customers.",
        "https://acme.example.com",
        facets,
    )
    assert not ok

    ok, reason, _ = _validate_candidate_facets(
        "Zoom",
        "Zoom is a video communications company offering video conferencing.",
        "Zoom provides video conferencing and online meetings for teams.",
        "https://zoom.us",
        facets,
    )
    assert ok, reason


def test_relation_extraction_needs_brand_plus_terms():
    # Brand + required terms in one sentence -> evidence returned.
    rel = _extract_category_relation(
        "Dropbox is a file hosting service that offers cloud storage.",
        "Dropbox",
        ["cloud", "storage"],
        2,
    )
    assert rel is not None
    # Broad suite sentence never identifies the suite itself as the category,
    # even though the brand token appears next to both category terms.
    assert (
        _extract_category_relation(
            "Google Cloud Platform is a cloud computing platform.",
            "Google Cloud Platform",
            ["cloud", "storage"],
            2,
        )
        is None
    )


# ---------------- Issue 2: domain identity ----------------

def test_similarity_accepts_legit_hosts_rejects_generic_overlap():
    assert _host_similarity_score("Keeper", "keepersecurity.com") >= 0.5
    assert _host_similarity_score("Trust Wallet", "trustwallet.com") >= 0.5
    assert _host_similarity_score("Google Cloud Storage", "cloud.google.com") >= 0.5
    assert _host_similarity_score("Google Cloud Storage", "cloudberrylab.com") < 0.5


def test_gcs_resolves_to_google_host():
    with patch("prior.research._get_wiki_extlinks", return_value=[]), patch(
        "prior.research._search_ddg",
        return_value=[
            {
                "title": "Google Cloud Storage | Google Cloud",
                "snippet": "Object storage from Google Cloud. Official documentation and pricing.",
                "url": "https://cloud.google.com/storage",
            }
        ],
    ):
        info = resolve_official_domain("Google Cloud Storage", "Google_Cloud_Storage")
        assert info is not None
        assert info["domain"] == "cloud.google.com"


def test_gcs_rejects_cloudberrylab():
    with patch("prior.research._get_wiki_extlinks", return_value=[]), patch(
        "prior.research._search_ddg",
        return_value=[
            {
                "title": "CloudBerry Backup",
                "snippet": "Backup software for cloud storage.",
                "url": "https://www.cloudberrylab.com/backup",
            }
        ],
    ):
        assert resolve_official_domain("Google Cloud Storage", "Some_Title") is None


def test_same_name_brand_hostname_passes():
    with patch("prior.research._get_wiki_extlinks", return_value=[]), patch(
        "prior.research._search_ddg",
        return_value=[
            {
                "title": "Bitwarden Official Site",
                "snippet": "Bitwarden open source password manager. Download the official apps.",
                "url": "https://bitwarden.com/",
            }
        ],
    ):
        info = resolve_official_domain("Bitwarden", "")
        assert info is not None
        assert info["domain"] == "bitwarden.com"


def test_product_to_parent_domain_passes_with_relationship_evidence():
    """First entity token ('pixel') is absent from the legitimate hostname,
    but the result explicitly names the product AND links the host org."""
    with patch("prior.research._get_wiki_extlinks", return_value=[]), patch(
        "prior.research._search_ddg",
        return_value=[
            {
                "title": "Pixel 8 - Google Store",
                "snippet": "Buy Pixel 8 from the Google Store. Official pricing and support.",
                "url": "https://store.google.com/pixel",
            }
        ],
    ):
        info = resolve_official_domain("Pixel 8", "")
        assert info is not None
        assert info["domain"] == "store.google.com"


def test_unrelated_shared_generic_token_domain_fails():
    with patch("prior.research._get_wiki_extlinks", return_value=[]), patch(
        "prior.research._search_ddg",
        return_value=[
            {
                "title": "Best Cloud Storage Providers of 2026",
                "snippet": "We compared the top cloud storage services and their prices.",
                "url": "https://bestcloudstorage.com/providers",
            }
        ],
    ):
        assert resolve_official_domain("Google Cloud Storage", "") is None


def test_wiki_token_absent_extlink_alone_is_not_official():
    """Provenance is not proof: a token-absent extlink must NOT become the
    official domain merely by appearing on the entity's Wikipedia page."""
    with patch(
        "prior.research._get_wiki_extlinks",
        return_value=["https://store.google.com/pixel"],
    ), patch("prior.research._search_ddg", return_value=[]):
        assert resolve_official_domain("Pixel 8", "Pixel_8") is None


def test_wiki_unrelated_first_extlink_is_skipped_for_valid_one():
    """First non-excluded extlink unrelated -> skipped; later similar host wins."""
    with patch(
        "prior.research._get_wiki_extlinks",
        return_value=[
            "https://partner.example.org/about",
            "https://bitwarden.com/",
        ],
    ):
        info = resolve_official_domain("Bitwarden", "Bitwarden")
        assert info is not None
        assert info["domain"] == "bitwarden.com"


def test_wiki_high_similarity_extlink_passes():
    with patch(
        "prior.research._get_wiki_extlinks",
        return_value=["https://keepersecurity.com/"],
    ):
        info = resolve_official_domain("Keeper", "Keeper_(password_manager)")
        assert info is not None
        assert "keepersecurity.com" in info["domain"]


def test_multi_token_first_token_only_is_not_naming():
    from prior.research import _result_names_entity

    assert not _result_names_entity(
        "Google Drive", "Official Google product", "Google Cloud Storage"
    )
    assert not _result_names_entity(
        "Google Cloud Platform", "Cloud computing by Google", "Google Cloud Storage"
    )
    # Genuine full naming still counts.
    assert _result_names_entity(
        "Google Cloud Storage", "Object storage pricing", "Google Cloud Storage"
    )
    # Parent-domain case genuinely naming the product still counts.
    assert _result_names_entity("Pixel 8 - Google Store", "Buy Pixel 8", "Pixel 8")


def test_gcs_rejects_google_drive_result():
    """Same-brand different product must not resolve via token coincidence."""
    with patch("prior.research._get_wiki_extlinks", return_value=[]), patch(
        "prior.research._search_ddg",
        return_value=[
            {
                "title": "Google Drive - Official Google product",
                "snippet": "Personal cloud storage from Google.",
                "url": "https://drive.google.com/",
            }
        ],
    ):
        assert resolve_official_domain("Google Cloud Storage", "") is None


def test_ambiguous_evidence_yields_no_domain():
    with patch("prior.research._get_wiki_extlinks", return_value=[]), patch(
        "prior.research._search_ddg",
        return_value=[
            {
                "title": "Nimbus Drive",
                "snippet": "Nimbus Drive page.",
                "url": "https://example.com/nimbus-drive",
            }
        ],
    ):
        assert resolve_official_domain("Nimbus Drive", "") is None


# ---------------- UAT 76624 real-failure regressions ----------------
# These reproduce the exact production failure classes: URL-path bait domains,
# suite-component category admission, and plan-word pricing fabrication.

def test_76624_cloudberry_path_bait_rejected_valid_host_wins():
    """Real case: GCS wiki extlinks list the cloudberrylab article URL first.
    Path text must not confer ownership; cloud.google.com must win."""
    with patch(
        "prior.research._get_wiki_extlinks",
        return_value=[
            "http://www.cloudberrylab.com/blog/choosing-online-backup-storage-google-cloud-storage-vs-google-drive/",
            "https://cloud.google.com/storage/",
        ],
    ):
        info = resolve_official_domain("Google Cloud Storage", "Google_Cloud_Storage")
        assert info is not None
        assert info["domain"] == "cloud.google.com"


def test_76624_datacenterknowledge_path_bait_rejected():
    """Real case: Amazon_S3 extlinks list the datacenterknowledge article
    before aws.amazon.com/s3. The article host must not win."""
    with patch(
        "prior.research._get_wiki_extlinks",
        return_value=[
            "http://www.datacenterknowledge.com/archives/2010/03/09/amazon-s3-now-hosts-100-billion-objects/",
            "http://aws.amazon.com/s3/",
        ],
    ):
        info = resolve_official_domain("Amazon S3", "Amazon_S3")
        assert info is not None
        assert info["domain"] == "aws.amazon.com"


def test_76624_entity_in_query_string_confirms_nothing():
    with patch(
        "prior.research._get_wiki_extlinks",
        return_value=["https://example.com/search?q=Amazon+S3"],
    ), patch("prior.research._search_ddg", return_value=[]):
        assert resolve_official_domain("Amazon S3", "Amazon_S3") is None


def test_76624_exact_entity_slug_confirms_nothing():
    with patch(
        "prior.research._get_wiki_extlinks",
        return_value=["https://example.com/docs/amazon-s3"],
    ), patch("prior.research._search_ddg", return_value=[]):
        assert resolve_official_domain("Amazon S3", "Amazon_S3") is None


def test_76624_suite_component_sentence_rejected():
    """Real GCP admission case: storage as one component of a broad suite."""
    facets = _cloud_facets()
    ok, reason, _ = _validate_candidate_facets(
        "Google Cloud Platform",
        "Google Cloud is a suite of cloud computing services.",
        "Google Cloud Platform provides modular cloud services including computing, data storage, data analytics, and machine learning.",
        "https://en.wikipedia.org/wiki/Google_Cloud_Platform",
        facets,
    )
    assert not ok
    assert "relational" in reason.lower() or "category" in reason.lower()


def test_76624_scattered_feature_list_rejected():
    facets = _cloud_facets()
    ok, _, _ = _validate_candidate_facets(
        "Acme Cloud",
        "Acme Cloud is a platform for compute, databases, cloud backups and storage.",
        "Acme Cloud offers virtual machines, databases, and cloud backup storage options.",
        "https://acme.example.com",
        facets,
    )
    assert not ok


def test_76624_compact_identity_relation_passes():
    facets = _cloud_facets()
    ok, reason, _ = _validate_candidate_facets(
        "Dropbox",
        "Dropbox is a cloud storage service for teams.",
        "Dropbox offers file synchronization.",
        "https://dropbox.com",
        facets,
    )
    assert ok, reason


def test_76624_cloud_based_storage_relation_passes():
    facets = _cloud_facets()
    ok, reason, _ = _validate_candidate_facets(
        "Nimbus",
        "Nimbus provides cloud-based storage for teams.",
        "Nimbus offers file synchronization.",
        "https://nimbus.example.com",
        facets,
    )
    assert ok, reason


def test_76624_second_category_component_rejected():
    facets = _vc_facets()
    ok, _, _ = _validate_candidate_facets(
        "OmniCorp",
        "OmniCorp offers a suite of tools.",
        "OmniCorp offers a suite of tools including video, messaging, and conferencing for enterprises.",
        "https://omnicorp.example.com",
        facets,
    )
    assert not ok


def test_76624_unrelated_clauses_rejected():
    facets = _cloud_facets()
    ok, _, _ = _validate_candidate_facets(
        "Acme",
        "Acme was founded in 2020.",
        "Its cloud division handles storage for a few clients.",
        "https://acme.example.com",
        facets,
    )
    assert not ok


def _pricing_with_mocked_fetch(monkeypatch, pages: dict):
    from prior.research import extract_first_party_pricing

    def mock_fetch(url):
        for key, body in pages.items():
            if key in url:
                return body
        return ""

    monkeypatch.setattr("prior.research._fetch_page_text", mock_fetch)
    return extract_first_party_pricing


def test_76624_plan_words_without_price_are_truthful(monkeypatch):
    extract_first_party_pricing = _pricing_with_mocked_fetch(
        monkeypatch,
        {"/pricing": "<html><body>" + "Our plans include Free plan, Premium plan, Business and Enterprise tiers with great features. " * 12 + "</body></html>"},
    )
    val, sources, _ = extract_first_party_pricing(
        "Google Cloud Platform", "cloud.google.com", "https://cloud.google.com", ""
    )
    assert val == "Not publicly disclosed in the retrieved source."
    assert sources == []
    assert "Free plan" not in val
    assert "Business / Enterprise" not in val


def test_76624_nav_footer_plan_words_not_pricing(monkeypatch):
    extract_first_party_pricing = _pricing_with_mocked_fetch(
        monkeypatch,
        {"/pricing": "<html><body>" + "Home Products Free Trial Premium Support Business Contact Enterprise Login Status. " * 12 + "</body></html>"},
    )
    val, _, _ = extract_first_party_pricing(
        "MysteryBox", "mysterybox.example", "https://mysterybox.example", ""
    )
    assert val == "Not publicly disclosed in the retrieved source."
    assert "Premium" not in val


def test_76624_explicit_plan_price_pairing_passes(monkeypatch):
    extract_first_party_pricing = _pricing_with_mocked_fetch(
        monkeypatch,
        {"/pricing": "<html><body>" + "Our Acme Store Business costs $10 per user/month with annual billing and admin controls. " * 8 + "</body></html>"},
    )
    val, sources, _ = extract_first_party_pricing(
        "Acme Store", "acmestore.example", "https://acmestore.example", ""
    )
    assert "$10" in val
    assert len(sources) > 0


def test_76624_usage_rate_passes(monkeypatch):
    extract_first_party_pricing = _pricing_with_mocked_fetch(
        monkeypatch,
        {"/pricing": "<html><body>" + "Simple Acme Store storage pricing at $0.023 per GB-month with no minimum fees ever. " * 8 + "</body></html>"},
    )
    val, sources, _ = extract_first_party_pricing(
        "Acme Store", "acmestore.example", "https://acmestore.example", ""
    )
    assert "$0.023 per GB-month" in val
    assert len(sources) > 0


def test_76624_payg_model_statement_without_tiers(monkeypatch):
    extract_first_party_pricing = _pricing_with_mocked_fetch(
        monkeypatch,
        {"/pricing": "<html><body>" + "Acme Store uses pay-as-you-go pricing based on usage across all regions worldwide. " * 8 + "</body></html>"},
    )
    val, _, _ = extract_first_party_pricing(
        "Acme Store", "acmestore.example", "https://acmestore.example", ""
    )
    assert "pay-as-you-go" in val.lower()
    assert "Free plan" not in val
    assert "Business / Enterprise" not in val


def test_76668_generic_google_cloud_page_not_gcs_pricing(monkeypatch):
    """Exact 76668 failure: Google Cloud-wide statement must not become
    Google Cloud Storage pricing."""
    extract_first_party_pricing = _pricing_with_mocked_fetch(
        monkeypatch,
        {"/pricing": "<html><body>" + "$300 in free credits 20+ free products Only pay for what you use With Google Cloud\u2019s pay-as-you-go pricing structure, you only pay for the services you use. " * 6 + "</body></html>"},
    )
    val, sources, _ = extract_first_party_pricing(
        "Google Cloud Storage", "cloud.google.com", "https://cloud.google.com", ""
    )
    assert val == "Not publicly disclosed in the retrieved source."
    assert sources == []


def test_76668_generic_aws_page_not_s3_pricing(monkeypatch):
    """Exact 76668 failure: AWS-wide statement must not become S3 pricing."""
    extract_first_party_pricing = _pricing_with_mocked_fetch(
        monkeypatch,
        {"/pricing": "<html><body>" + "AWS offers you a pay-as-you-go approach for pricing for the vast majority of our cloud services. " * 8 + "</body></html>"},
    )
    val, sources, _ = extract_first_party_pricing(
        "Amazon S3", "aws.amazon.com", "https://aws.amazon.com", ""
    )
    assert val == "Not publicly disclosed in the retrieved source."
    assert sources == []


def test_76668_product_specific_parent_domain_page_passes(monkeypatch):
    """Child product on parent domain passes when the pricing URL itself is
    product-specific, even without an entity mention in the text."""
    extract_first_party_pricing = _pricing_with_mocked_fetch(
        monkeypatch,
        {"/storage/pricing": "<html><body>" + "Object storage is $0.020 per GB-month for standard class in all regions. " * 8 + "</body></html>"},
    )
    val, sources, _ = extract_first_party_pricing(
        "Google Cloud Storage", "cloud.google.com", "https://cloud.google.com/storage", ""
    )
    assert "$0.020 per GB-month" in val
    assert len(sources) > 0


def test_76668_company_wide_page_without_candidate_is_truthful(monkeypatch):
    extract_first_party_pricing = _pricing_with_mocked_fetch(
        monkeypatch,
        {"/pricing": "<html><body>" + "Our company-wide pay-as-you-go pricing covers all cloud services and support plans. " * 8 + "</body></html>"},
    )
    val, _, _ = extract_first_party_pricing(
        "Nimbus", "nimbus.example", "https://nimbus.example", ""
    )
    assert val == "Not publicly disclosed in the retrieved source."


def test_76668_live_gcp_storage_block_rejected():
    """Actual 76668 evidence shape: the unsplit 'Storage and databases'
    section block lists Cloud Storage as one item among many. It never
    identifies Google Cloud Platform itself as a cloud storage service."""
    facets = _cloud_facets()
    block = (
        "=== Storage and databases ===\n"
        "Cloud Storage \u2013 Object storage with integrated edge caching to store unstructured data\n"
        "Cloud SQL \u2013 Database as a Service based on MySQL, PostgreSQL and Microsoft SQL Server\n"
        "Cloud Bigtable \u2013 Managed NoSQL database service\n"
        "Filestore \u2013 High-performance file storage for Google Cloud users"
    )
    ok, reason, _ = _validate_candidate_facets(
        "Google Cloud Platform",
        "Google Cloud is a suite of cloud computing services.",
        block,
        "https://en.wikipedia.org/wiki/Google_Cloud_Platform",
        facets,
    )
    assert not ok
    assert "relational" in reason.lower() or "category" in reason.lower()
