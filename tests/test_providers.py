from prior.providers import active_provider
from prior.providers.base import VIRTUALS_NOT_CONFIGURED, ProviderError
from prior.providers.local import LOCAL_NAME, LOCAL_SOURCE, LocalResearchProvider
from prior.providers.virtuals import VirtualsAcpProvider
from prior.job_spec import parse_job


def test_local_provider_is_labelled_local_not_virtuals(monkeypatch):
    monkeypatch.setattr("prior.providers.acp_enabled", lambda: False)
    monkeypatch.setattr("prior.providers.local_provider_enabled", lambda: True)
    provider = active_provider()
    assert isinstance(provider, LocalResearchProvider)
    offers = provider.find_providers(parse_job("Research the top five AI wallet companies."))
    assert offers[0].name == LOCAL_NAME
    assert offers[0].source == LOCAL_SOURCE
    assert "virtuals" not in offers[0].name.lower()
    assert "virtuals" not in offers[0].summary.lower() or "not virtuals" in offers[0].summary.lower()


def test_virtuals_does_not_fall_back_to_local(monkeypatch):
    monkeypatch.setattr("prior.providers.acp_enabled", lambda: True)
    monkeypatch.setattr("prior.providers.local_provider_enabled", lambda: True)
    monkeypatch.setattr("prior.providers.virtuals.acp_ready", lambda: False)
    monkeypatch.setattr(
        "prior.providers.virtuals.missing_virtuals_credentials",
        lambda role="buyer": ["BUYER_WALLET_ADDRESS", "BUYER_WALLET_ID", "BUYER_SIGNER_PRIVATE_KEY"],
    )
    provider = active_provider()
    assert isinstance(provider, VirtualsAcpProvider)
    try:
        provider.find_providers(parse_job("Research wallets"))
        raise AssertionError("should have failed")
    except ProviderError as exc:
        assert "Virtuals credentials are not configured" in str(exc)
        assert "BUYER_WALLET_ADDRESS" in str(exc)


def test_no_provider_is_honest(monkeypatch):
    monkeypatch.setattr("prior.providers.acp_enabled", lambda: False)
    monkeypatch.setattr("prior.providers.local_provider_enabled", lambda: False)
    try:
        active_provider()
        raise AssertionError("should have failed")
    except ProviderError as exc:
        assert str(exc) == VIRTUALS_NOT_CONFIGURED
