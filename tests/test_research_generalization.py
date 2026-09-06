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
        "dropbox",
        ["cloud", "storage"],
        2,
    )
    assert rel is not None
    # Brand present but category terms split/absent -> no relation.
    assert (
        _extract_category_relation(
            "Google Cloud Platform is a cloud computing platform.",
            "google",
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


def test_wiki_provenance_covers_token_absent_legitimate_host():
    """Exact entity page provenance must not auto-fail when the first token
    is absent from a legitimate hostname."""
    with patch(
        "prior.research._get_wiki_extlinks",
        return_value=["https://store.google.com/pixel"],
    ):
        info = resolve_official_domain("Pixel 8", "Pixel_8")
        assert info is not None
        assert info["domain"] == "store.google.com"


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
