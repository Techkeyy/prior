"""Refresh must never clobber fund/hire intent persisted mid-poll (ACP 78280).

Production failure: a poll GET loaded its record snapshot, entered a slow
bridge status call, and saved the stale snapshot AFTER fund/prepare had
persisted its intent — so fund/execute found nothing. FastAPI runs sync
endpoints in a threadpool, so refresh and prepare genuinely overlap.
"""

import threading
import time

import pytest

from prior import hiring as hiring_mod
from prior import jobs as jobs_mod
from prior import service

WS = "ws_race_280"
BUDGET = {"amount": "0.03", "symbol": "USDC", "decimals": 6,
          "tokenAddress": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"}


@pytest.fixture
def race_env(monkeypatch):
    monkeypatch.setenv("ACP_ENABLED", "true")
    monkeypatch.setenv("PRIOR_ENABLE_ACP_WRITES", "true")
    monkeypatch.setenv("BUYER_WALLET_ADDRESS", "0x" + "b0" * 20)
    monkeypatch.setenv("BUYER_WALLET_ID", "buyer-wallet-test")
    monkeypatch.setenv("BUYER_SIGNER_PRIVATE_KEY", "test-signer-key")


def _hired_record():
    record = service.specify(WS, "Review this Base USDC approval for signing safety.")
    record.status = "hired"
    record.provider = {
        "id": "0xabc", "name": "COINGAZURA", "summary": "", "price_label": "0.03",
        "source": "virtuals-acp", "network": "Virtuals ACP",
        "wallet_address": "0xabc", "offering_name": "coingazura_tx_explain_allow_review_avoid_micro",
    }
    record.acp_job_id = "78280"
    record.acp_phase = "open"
    record.hire_state = "created"
    record.hire_plan = {"idempotency_key": "hire_race", "price_value": 0.03,
                        "contract_fingerprint": hiring_mod.contract_fingerprint(record.contract)}
    return jobs_mod.put(record)


def _gated_bridge(monkeypatch, release_after_prepare):
    import time as _time

    import prior.providers.virtuals as virtuals_mod

    live_deadline = str(int(_time.time()) + 3600)
    status_calls = {"n": 0}
    loaded = threading.Event()

    def _fake(args):
        if args[0] == "status":
            status_calls["n"] += 1
            if status_calls["n"] == 1:
                loaded.set()
                assert release_after_prepare.wait(timeout=15), "prepare never finished"
            return {"ok": True, "jobId": "78280", "phase": "open", "chainId": 8453,
                    "sessionStatus": "open", "hasBudget": True, "funded": False,
                    "budget": dict(BUDGET), "expiredAt": live_deadline, "deliverable": None}
        if args[0] == "fund":
            return {"ok": True, "jobId": args[1], "action": "fund", "phase": "funded"}
        raise AssertionError(f"unexpected bridge command: {args}")

    monkeypatch.setattr(virtuals_mod, "_bridge", _fake)
    return loaded


def test_slow_poll_refresh_preserves_prepared_fund_intent(race_env, monkeypatch):
    release = threading.Event()
    loaded = _gated_bridge(monkeypatch, release)
    record = _hired_record()
    worker = threading.Thread(target=service.refresh, args=(WS, record.id), daemon=True)
    worker.start()
    assert loaded.wait(timeout=10), "slow poll never entered the bridge"
    plan = service.prepare_fund(WS, record.id)
    assert plan["amount"] == 0.03
    release.set()
    worker.join(timeout=20)
    stored = jobs_mod.get(record.id, WS)
    assert stored is not None
    assert stored.fund_state == "fund_prepared", f"intent wiped by stale refresh: {stored.fund_state}"
    assert stored.fund_intent is not None
    out = service.execute_fund(WS, record.id)
    assert out.fund_state == "funded"


def test_slow_poll_refresh_preserves_hire_plan(race_env, monkeypatch):
    release = threading.Event()
    loaded = _gated_bridge(monkeypatch, release)
    record = service.specify(WS + "_hire", "Review this Base USDC approval for signing safety.")
    record.status = "hired"
    record.provider = {
        "id": "0xabc", "name": "COINGAZURA", "summary": "", "price_label": "0.03",
        "source": "virtuals-acp", "network": "Virtuals ACP",
        "wallet_address": "0xabc", "offering_name": "coingazura_tx_explain_allow_review_avoid_micro",
    }
    record.acp_job_id = "78280"
    record.acp_phase = "open"
    record.hire_state = "created"
    record = jobs_mod.put(record)
    worker = threading.Thread(target=service.refresh, args=(WS + "_hire", record.id), daemon=True)
    worker.start()
    assert loaded.wait(timeout=10)
    stored = jobs_mod.get(record.id, WS + "_hire")
    stored.hire_state = "prepared"
    stored.hire_plan = {"idempotency_key": "hire_keepme", "price_value": 0.03,
                        "contract_fingerprint": hiring_mod.contract_fingerprint(stored.contract)}
    jobs_mod.put(stored)
    release.set()
    worker.join(timeout=20)
    after = jobs_mod.get(record.id, WS + "_hire")
    assert after is not None
    assert (after.hire_plan or {}).get("idempotency_key") == "hire_keepme"
    assert after.hire_state == "prepared"


def test_refresh_still_applies_observed_funded_transition(race_env, monkeypatch):
    import prior.providers.virtuals as virtuals_mod

    live_deadline = str(int(time.time()) + 3600)

    def _fake(args):
        if args[0] == "status":
            return {"ok": True, "jobId": "78280", "phase": "open", "chainId": 8453,
                    "sessionStatus": "funded", "hasBudget": True, "funded": True,
                    "budget": dict(BUDGET), "expiredAt": live_deadline, "deliverable": None}
        raise AssertionError(args)

    monkeypatch.setattr(virtuals_mod, "_bridge", _fake)
    record = _hired_record()
    out = service.refresh(WS, record.id)
    assert out.fund_state == "funded"
