"""Cross-category research generalization regression tests.

Proves that password-manager-specific factual defaults can never leak into
unrelated categories (e.g. cloud storage services), that official domains must
belong to the discovered entity, that unsupported fields are reported
truthfully, that comparison synthesis only uses verified values, and that
execution order across categories cannot contaminate results.

All tests are offline (first-party page fetches are mocked); no new
category-specific hardcoding is permitted by test_zero_category_hardcoding.
"""

from unittest.mock import patch

from prior.job_spec import parse_job
from prior.contract import build_contract
from prior import research
from prior.research import (
    extract_facets,
    extract_first_party_platforms,
    extract_first_party_pricing,
    extract_first_party_strength,
    extract_first_party_weakness,
    resolve_official_domain,
    _comparative_summary,
    _validate_candidate_facets,
)

EMPTY_FETCH = patch("prior.research._fetch_page_text", return_value="")

PASSWORD_VAULT_MARKERS = (
    "password vault",
    "password-vault",
    "credential management",
    "autofill",
    "zero-knowledge encrypted password",
)

CLOUD_SPEC_RAW = (
    "Research three cloud storage services and compare their pricing, "
    "supported platforms, strengths, and weaknesses."
)
PM_SPEC_RAW = (
    "Research three password managers and compare their pricing, "
    "supported platforms, strengths, and weaknesses."
)


def test_zero_category_hardcoding():
    """No vendor/category-specific registries for the unrelated categories."""
    for attr in (
        "CLOUD_ENTITIES",
        "CLOUD_DOMAINS",
        "STORAGE_ENTITIES",
        "GOOGLE_DOMAINS",
        "AWS_DOMAINS",
        "CLOUDBERRY",
        "KEEPASS",
        "LASTPASS",
        "KEEPER",
    ):
        assert not hasattr(research, attr), attr


def test_password_manager_evidence_stays_category_specific():
    """Vendor branches still fire for genuine password-manager entities."""
    with EMPTY_FETCH:
        s, _, _ = extract_first_party_strength(
            "Keeper", "keepersecurity.com", "https://keepersecurity.com", ""
        )
        assert "Zero-knowledge AES-256" in s

        p, src, _ = extract_first_party_pricing(
            "KeePass", "keepass.info", "https://keepass.info", "free and open source"
        )
        assert "Free and open-source" in p
        assert len(src) > 0


def test_unrelated_category_cannot_inherit_pm_defaults():
    """Unknown entities/domains must not receive password-manager templates."""
    with EMPTY_FETCH:
        s, _, _ = extract_first_party_strength(
            "Google Cloud Storage",
            "cloud.google.com",
            "https://cloud.google.com",
            "object storage service",
        )
        assert "Could not verify" in s

        p, _, _ = extract_first_party_pricing(
            "Google Cloud Storage",
            "cloud.google.com",
            "https://cloud.google.com",
            "object storage service",
        )
        assert p == "Not publicly disclosed in the retrieved source."

        pl, _, _ = extract_first_party_platforms(
            "Google Cloud Storage",
            "cloud.google.com",
            "https://cloud.google.com",
            "object storage service",
        )
        assert "Could not verify" in pl


def test_zero_password_vault_leakage_in_unrelated_category():
    """No password-vault terminology may appear for cloud-storage research."""
    with EMPTY_FETCH:
        outputs = []
        for fn in (
            extract_first_party_strength,
            extract_first_party_pricing,
            extract_first_party_platforms,
        ):
            val, _, _ = fn(
                "Amazon S3",
                "aws.amazon.com",
                "https://aws.amazon.com",
                "object storage service",
            )
            outputs.append(val)
        wk, _, _, _ = extract_first_party_weakness(
            "Amazon S3", "aws.amazon.com", "https://aws.amazon.com", "object storage"
        )
        outputs.append(wk)
        blob = " ".join(outputs).lower()
        for marker in PASSWORD_VAULT_MARKERS:
            assert marker not in blob, marker


def test_official_domain_must_correspond_to_entity():
    """Brand-token match: google entity resolves to a google host."""
    with patch("prior.research._get_wiki_extlinks", return_value=[]), patch(
        "prior.research._search_ddg",
        return_value=[
            {
                "title": "Google Cloud Storage",
                "snippet": "object storage",
                "url": "https://cloud.google.com/storage",
            }
        ],
    ):
        info = resolve_official_domain("Google Cloud Storage", "Google_Cloud_Storage")
        assert info is not None
        assert "google" in info["domain"]


def test_unrelated_vendor_domain_is_rejected():
    """cloudberrylab.com must never resolve as the domain of Google Cloud Storage."""
    with patch("prior.research._get_wiki_extlinks", return_value=[]), patch(
        "prior.research._search_ddg",
        return_value=[
            {
                "title": "CloudBerry Backup",
                "snippet": "backup",
                "url": "https://www.cloudberrylab.com/backup",
            }
        ],
    ):
        assert (
            resolve_official_domain("Google Cloud Storage", "Some_Title") is None
        )


def test_unsupported_pricing_reported_truthfully():
    with EMPTY_FETCH:
        p, src, ev = extract_first_party_pricing("MysteryBox", "", "", "")
        assert p == "Not publicly disclosed in the retrieved source."
        assert src == []
        assert ev != ""


def test_unsupported_platforms_reported_truthfully():
    with EMPTY_FETCH:
        pl, src, ev = extract_first_party_platforms("MysteryBox", "", "", "")
        assert "Could not verify" in pl
        assert src == []
        assert ev != ""


def test_strengths_require_entity_specific_evidence():
    with EMPTY_FETCH:
        s, src, ev = extract_first_party_strength("MysteryBox", "mysterybox.example", "https://mysterybox.example", "generic text")
        assert "Could not verify" in s
        assert src == []
        assert ev != ""


def test_weaknesses_require_entity_specific_evidence():
    with EMPTY_FETCH:
        w, _, _, _ = extract_first_party_weakness("MysteryBox", "mysterybox.example", "https://mysterybox.example", "generic text")
        assert "Could not verify" in w


def test_comparison_synthesis_uses_only_verified_values():
    findings = [
        {
            "name": "Alpha Store",
            "pricing": "Not publicly disclosed in the retrieved source.",
            "supported_platforms": "Windows, Linux",
            "supported platforms": "Windows, Linux",
            "strengths": "Could not verify a specific strength from the retrieved sources.",
            "weaknesses": "Could not verify a specific weakness from the retrieved sources.",
        },
        {
            "name": "Beta Store",
            "pricing": "$5/mo starter",
            "supported_platforms": "Could not verify supported platforms from the retrieved sources.",
            "supported platforms": "Could not verify supported platforms from the retrieved sources.",
            "strengths": "Scales to exabytes per vendor docs",
            "weaknesses": "Egress fees apply per vendor docs",
        },
    ]
    summary = _comparative_summary(findings)
    assert "Side-by-side comparison" in summary
    assert "$5/mo starter" in summary
    assert "Scales to exabytes" in summary
    for marker in PASSWORD_VAULT_MARKERS:
        assert marker not in summary.lower()
    # Unavailable cells must be marked unavailable, never filled with templates.
    assert "unavailable" in summary.lower()
    assert "Free, Premium" not in summary
    assert "Browser Extensions" not in summary


def _cloud_field_blob():
    with EMPTY_FETCH:
        s, _, _ = extract_first_party_strength(
            "Google Cloud Storage", "cloud.google.com", "https://cloud.google.com", "object storage"
        )
        p, _, _ = extract_first_party_pricing(
            "Google Cloud Storage", "cloud.google.com", "https://cloud.google.com", "object storage"
        )
        pl, _, _ = extract_first_party_platforms(
            "Google Cloud Storage", "cloud.google.com", "https://cloud.google.com", "object storage"
        )
        return f"{s} {p} {pl}".lower()


def _pm_field_blob():
    with EMPTY_FETCH:
        s, _, _ = extract_first_party_strength(
            "Keeper", "keepersecurity.com", "https://keepersecurity.com", ""
        )
        return s.lower()


def test_category_a_then_b_no_contamination():
    assert "password vault" in _pm_field_blob() or "zero-knowledge" in _pm_field_blob()
    blob = _cloud_field_blob()
    for marker in PASSWORD_VAULT_MARKERS:
        assert marker not in blob, marker


def test_category_b_then_a_no_contamination():
    blob_b = _cloud_field_blob()
    blob_a = _pm_field_blob()
    for marker in PASSWORD_VAULT_MARKERS:
        assert marker not in blob_b, marker
    assert "zero-knowledge" in blob_a


def test_two_materially_different_categories_work():
    pm_spec = parse_job(PM_SPEC_RAW)
    pm_facets = extract_facets(pm_spec)
    assert pm_facets.domain == "password_manager"

    cloud_spec = parse_job(CLOUD_SPEC_RAW)
    cloud_facets = extract_facets(cloud_spec)
    # Cloud request must not be classified as a password-manager job.
    assert cloud_facets.domain != "password_manager"

    cloud_contract = build_contract(cloud_spec, [])
    assert "pricing" in cloud_contract.deliverables
    assert "supported platforms" in cloud_contract.deliverables

    # Password-manager validation still rejects non-managers...
    ok, _, _ = _validate_candidate_facets(
        "Dropbox",
        "cloud file hosting and synchronization service",
        "file hosting service operated by Dropbox Inc",
        "https://dropbox.com",
        pm_facets,
    )
    assert not ok

    # ...and unknown-category selection requires entity-specific mention.
    ok, reason, _ = _validate_candidate_facets(
        "Unrelated Corp",
        "does something entirely different",
        "no mention of the candidate at all here",
        "https://example.com",
        cloud_facets,
    )
    assert not ok
    assert "entity-specific" in reason.lower()
