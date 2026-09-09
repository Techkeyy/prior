"""Expiry truthfulness: PRIOR surfaces EXPIRED while preserving raw ACP state.

Covers: active-before-deadline, expired-after-deadline, funding refused on
expired/unknown deadlines, read-only polling of expired jobs, raw phase
preservation, and no eternal WAIT.
"""

import time

import pytest

from prior import hiring as hiring_mod
from prior import jobs as jobs_mod
from prior import service


def _hired(ws, expired_at=None):
    record = service.specify(ws, "Research the top five AI wallet companies and compare their features.")
    record.status = "hired"
    record.provider = {
        "id": "0xabc", "name": "ZIZI", "summary": "", "price_label": "",
        "source": "virtuals-acp", "network": "Virtuals ACP",
        "wallet_address": "0xabc", "offering_name": "crypto_news_brief",
    }
    record.acp_job_id = "77768"
    record.acp_phase = "open"
    record.acp_expired_at = expired_at
    return jobs_mod.put(record)


def _bridge_fake(monkeypatch, payload):
    import prior.providers.virtuals as virtuals_mod

    calls: list[list] = []

    def _fake(args):
        calls.append(list(args))
        assert args[0] == "status"
        return dict(payload)

    monkeypatch.setenv("ACP_ENABLED", "true")
    monkeypatch.setenv("BUYER_WALLET_ADDRESS", "0x" + "b0" * 20)
    monkeypatch.setenv("BUYER_WALLET_ID", "buyer-wallet-test")
    monkeypatch.setenv("BUYER_SIGNER_PRIVATE_KEY", "test-signer-key")
    monkeypatch.setattr(virtuals_mod, "_bridge", _fake)
    return calls


def test_open_before_deadline_is_active():
    future = str(int(time.time()) + 3600)
    assert hiring_mod.expiry_state(future) == "active"
    record = _hired("ws_exp_01", expired_at=future)
    assert hiring_mod.describe_lifecycle(record) == "active"


def test_open_after_deadline_is_expired_not_wait():
    past = str(int(time.time()) - 1800)
    assert hiring_mod.expiry_state(past) == "expired"
    record = _hired("ws_exp_02", expired_at=past)
    assert hiring_mod.describe_lifecycle(record) == "expired"
    # Raw external truth untouched.
    assert record.acp_phase == "open"
    assert record.status == "hired"


def test_expired_and_unknown_deadlines_refuse_funding():
    past = str(int(time.time()) - 10)
    expired = _hired("ws_exp_03", expired_at=past)
    with pytest.raises(hiring_mod.HireError):
        hiring_mod.ensure_fundable(expired)
    unknown = _hired("ws_exp_03b", expired_at=None)
    with pytest.raises(hiring_mod.HireError):
        hiring_mod.ensure_fundable(unknown)
    malformed = _hired("ws_exp_03c", expired_at="not-a-timestamp")
    with pytest.raises(hiring_mod.HireError):
        hiring_mod.ensure_fundable(malformed)
    live = _hired("ws_exp_03d", expired_at=str(int(time.time()) + 600))
    hiring_mod.ensure_fundable(live)


def test_polling_expired_job_stays_read_only(monkeypatch):
    calls = _bridge_fake(monkeypatch, {"ok": True, "jobId": "77768",
                                       "phase": "open", "expiredAt": str(int(time.time()) - 60)})
    _hired("ws_exp_04", expired_at=str(int(time.time()) - 60))
    job_id = jobs_mod.list_for("ws_exp_04")[0].id
    for _ in range(3):
        record = service.refresh("ws_exp_04", job_id)
    assert [c[0] for c in calls] == ["status", "status", "status"]
    assert hiring_mod.describe_lifecycle(record) == "expired"
    assert record.acp_phase == "open"


def test_raw_acp_phase_preserved_beside_prior_expired(monkeypatch):
    _bridge_fake(monkeypatch, {"ok": True, "jobId": "77768", "phase": "open",
                               "expiredAt": str(int(time.time()) - 5)})
    _hired("ws_exp_05", expired_at=str(int(time.time()) - 5))
    job_id = jobs_mod.list_for("ws_exp_05")[0].id
    record = service.refresh("ws_exp_05", job_id)
    assert record.acp_phase == "open"
    assert record.acp_expired_at is not None
    assert hiring_mod.describe_lifecycle(record) == "expired"


def test_expired_surfaces_through_job_api(monkeypatch):
    from fastapi.testclient import TestClient

    from prior.app import app

    _bridge_fake(monkeypatch, {"ok": True, "jobId": "77768", "phase": "open",
                               "expiredAt": str(int(time.time()) - 5)})
    client = TestClient(app)
    ws = client.get("/api/workspace").json()["workspace_id"]
    job = client.post("/api/jobs", json={
        "text": "Research the top five AI wallet companies and compare their features."}).json()
    stored = jobs_mod.get(job["id"], ws)
    assert stored is not None
    stored.status = "hired"
    stored.provider = {"source": "virtuals-acp", "network": "Virtuals ACP",
                       "wallet_address": "0xabc", "offering_name": "crypto_news_brief"}
    stored.acp_job_id = "77768"
    stored.acp_phase = "open"
    jobs_mod.put(stored)
    body = client.get(f"/api/jobs/{job['id']}").json()
    assert body["acp_phase"] == "open"
    assert body["prior_lifecycle"] == "expired"
