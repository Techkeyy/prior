"""Public ACP spend policy: per-job cap, semantic-first selection, frozen-price
integrity, single-active-job guard, global spend ceiling.

Production policy under test (pinned explicitly here; conftest lifts ceilings
for legacy suites):
  PRIOR_PUBLIC_MAX_JOB_USDC=0.50, PRIOR_PUBLIC_SPEND_LIMIT_USDC=1.00.

The bridge is always intercepted; no live ACP create/fund occurs anywhere.
"""

import pytest
from fastapi.testclient import TestClient

from prior import hiring as hiring_mod
from prior import jobs as jobs_mod
from prior import service
from prior.app import app
from prior.contract import build_contract
from prior.job_spec import parse_job
from prior.marketplace import NoCompatibleProvider, select_provider_for_spec

TEXT = "Research the top five AI wallet companies and compare their features."
W_A = "0x" + "aa" * 20
W_B = "0x" + "bb" * 20


@pytest.fixture
def policy_env(monkeypatch):
    monkeypatch.setenv("PRIOR_PUBLIC_MAX_JOB_USDC", "0.50")
    monkeypatch.setenv("PRIOR_PUBLIC_SPEND_LIMIT_USDC", "1.00")
    monkeypatch.setenv("ACP_ENABLED", "true")
    monkeypatch.setenv("PRIOR_ENABLE_ACP_WRITES", "true")
    monkeypatch.setenv("BUYER_WALLET_ADDRESS", "0x" + "b0" * 20)
    monkeypatch.setenv("BUYER_WALLET_ID", "buyer-wallet-test")
    monkeypatch.setenv("BUYER_SIGNER_PRIVATE_KEY", "test-signer-key")


def _agent(name, wallet, offerings, **kw):
    return {
        "id": f"id-{name}", "name": name,
        "description": kw.get("description", ""),
        "walletAddress": wallet,
        "lastActiveAt": kw.get("lastActiveAt", "2026-09-01T00:00:00Z"),
        "rating": kw.get("rating"), "isHidden": kw.get("isHidden", False),
        "chains": kw.get("chains", [{"chainId": 8453}]),
        "offerings": offerings,
    }


def _offering(name, desc, price, **kw):
    return {
        "name": name, "description": desc,
        "requirements": kw.get("requirements",
                               {"type": "object", "required": ["query"],
                                "properties": {"query": {"type": "string"}}}),
        "deliverable": kw.get("deliverable", ""),
        "priceType": kw.get("priceType", "fixed"),
        "priceValue": price,
        "requiredFunds": kw.get("requiredFunds", False),
        "slaMinutes": kw.get("slaMinutes", 10),
        "isHidden": kw.get("isHidden", False),
        "isPrivate": kw.get("isPrivate", False),
    }


RESEARCH_DESC = "Autonomous research and comparison with reports on any topic."


def _query(text=TEXT):
    spec = parse_job(text)
    contract = build_contract(spec, [])
    return spec, contract


def test_01_compatible_worker_at_003_eligible(policy_env):
    spec, contract = _query()
    market = [_agent("Cheap", W_A, [_offering("deep_research", RESEARCH_DESC, 0.03)])]
    sel = select_provider_for_spec(spec, contract, discover=lambda kw: market)
    assert sel.candidate.offering_name == "deep_research"
    assert sel.candidate.price_value == 0.03


def test_02_compatible_worker_exactly_at_050_eligible(policy_env):
    spec, contract = _query()
    market = [_agent("Exact", W_A, [_offering("deep_research", RESEARCH_DESC, 0.50)])]
    sel = select_provider_for_spec(spec, contract, discover=lambda kw: market)
    assert sel.candidate.price_value == 0.50


def test_03_worker_at_0500001_rejected_before_paid_execution(policy_env):
    spec, contract = _query()
    market = [_agent("Pricey", W_A, [_offering("deep_research", RESEARCH_DESC, 0.500001)])]
    with pytest.raises(NoCompatibleProvider) as exc:
        select_provider_for_spec(spec, contract, discover=lambda kw: market)
    assert "no funds were spent" in str(exc.value).lower()


def test_04_high_rated_over_cap_cannot_bypass(policy_env):
    spec, contract = _query()
    market = [_agent("Star", W_A, [_offering("deep_research", RESEARCH_DESC, 5.0)], rating=5.0)]
    with pytest.raises(NoCompatibleProvider):
        select_provider_for_spec(spec, contract, discover=lambda kw: market)


def test_05_cheap_incompatible_cannot_win_on_price(policy_env):
    spec, contract = _query()
    market = [
        _agent("CodeBot", W_A, [_offering(
            "code_scan", "Source code vulnerability scanner with CVSS scoring.",
            0.01,
            requirements={"type": "object", "required": ["code"],
                          "properties": {"code": {"type": "string"}}},
            deliverable="CVSS vulnerability report")]),
        _agent("Researcher", W_B, [_offering("deep_research", RESEARCH_DESC, 0.40)])]
    sel = select_provider_for_spec(spec, contract, discover=lambda kw: market)
    assert sel.candidate.offering_name == "deep_research"


def test_06_best_compatible_within_cap_selected(policy_env):
    spec, contract = _query()
    market = [
        _agent("Plain", W_A, [_offering("generic_research", "Research reports.", 0.03)]),
        _agent("Sharp", W_B, [_offering(
            "deep_research", "Autonomous research and comparison with reports on AI wallets.",
            0.40)])]
    sel = select_provider_for_spec(spec, contract, discover=lambda kw: market)
    assert sel.candidate.offering_name == "deep_research"
    assert sel.candidate.price_value == 0.40


def test_07_all_compatible_over_cap_clean_public_limit_zero_writes(policy_env, monkeypatch):
    import prior.providers.virtuals as virtuals_mod

    calls = []

    def _boom(args):
        calls.append(list(args))
        raise AssertionError(f"no ACP call may occur: {args}")

    monkeypatch.setattr(virtuals_mod, "_bridge", _boom)
    spec, contract = _query()
    market = [_agent("Pricey", W_A, [_offering("deep_research", RESEARCH_DESC, 2.50)])]
    with pytest.raises(NoCompatibleProvider) as exc:
        select_provider_for_spec(spec, contract, discover=lambda kw: market)
    msg = str(exc.value)
    assert "2.5" in msg and ("0.5" in msg or "0.50" in msg)
    assert "no funds were spent" in msg.lower()
    assert "Try another available agent" in msg
    assert calls == []


def _bridge_ok(monkeypatch, price=0.03, budget="0.03"):
    import time

    import prior.providers.virtuals as virtuals_mod

    calls = []
    live_deadline = str(int(time.time()) + 3600)

    def _fake(args):
        calls.append(list(args))
        if args[0] == "offering-refresh":
            return {"ok": True, "found": True, "chainId": 8453,
                    "agentName": "Cheap", "walletAddress": args[1],
                    "lastActiveAt": "2026-09-01T00:00:00Z", "chains": [8453],
                    "offering": {"name": args[2], "description": "Autonomous research",
                                 "requirements": {"type": "object", "required": ["query"],
                                                  "properties": {"query": {"type": "string"}}},
                                 "priceType": "fixed", "priceValue": price,
                                 "requiredFunds": False, "slaMinutes": 10,
                                 "isHidden": False, "isPrivate": False}}
        if args[0] == "create-offering-job":
            return {"ok": True, "jobId": "41234", "phase": "job.created",
                    "chainId": 8453, "providerAddress": args[1]}
        if args[0] == "status":
            return {"ok": True, "jobId": "41234", "phase": "open", "chainId": 8453,
                    "sessionStatus": "open", "hasBudget": True, "funded": False,
                    "budget": {"amount": budget, "symbol": "USDC", "decimals": 6,
                               "tokenAddress": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"},
                    "expiredAt": live_deadline, "deliverable": None}
        if args[0] == "fund":
            return {"ok": True, "jobId": args[1], "action": "fund", "phase": "funded"}
        raise AssertionError(f"unexpected bridge command: {args}")

    monkeypatch.setattr(virtuals_mod, "_bridge", _fake)
    return calls


def _specified(ws, text=TEXT):
    return service.specify(ws, text)


def test_08_price_or_provider_drift_after_confirmation_fails_closed(policy_env, monkeypatch):
    calls = _bridge_ok(monkeypatch, price=0.09)
    record = _specified("ws_pol_08")
    market = [_agent("Cheap", W_A, [_offering("deep_research", RESEARCH_DESC, 0.03)])]
    service.prepare_hire(record.workspace_id, record.id,
                         discover=lambda kw: market)
    with pytest.raises(hiring_mod.HireError):
        service.execute_hire(record.workspace_id, record.id)
    assert [c[0] for c in calls] == ["offering-refresh"]


def test_09_workspace_cannot_spam_parallel_paid_hires(policy_env, monkeypatch):
    calls = _bridge_ok(monkeypatch)
    market = [_agent("Cheap", W_A, [_offering("deep_research", RESEARCH_DESC, 0.03)])]
    first = _specified("ws_pol_09")
    service.prepare_hire(first.workspace_id, first.id, discover=lambda kw: market)
    service.execute_hire(first.workspace_id, first.id)
    assert [c[0] for c in calls].count("create-offering-job") == 1
    second = _specified("ws_pol_09", TEXT + " Also cover stablecoin wallets.")
    with pytest.raises(ValueError, match="still active"):
        service.prepare_hire(second.workspace_id, second.id, discover=lambda kw: market)
    assert [c[0] for c in calls].count("create-offering-job") == 1


def test_10_terminal_previous_job_allows_new_hire(policy_env, monkeypatch):
    calls = _bridge_ok(monkeypatch)
    market = [_agent("Cheap", W_A, [_offering("deep_research", RESEARCH_DESC, 0.03)])]
    first = _specified("ws_pol_10")
    service.prepare_hire(first.workspace_id, first.id, discover=lambda kw: market)
    done = service.execute_hire(first.workspace_id, first.id)
    stored = jobs_mod.get(done.id, done.workspace_id)
    stored.status = "rejected"
    stored.evaluation = "rejected"
    jobs_mod.put(stored)
    second = _specified("ws_pol_10", TEXT + " Also cover stablecoin wallets.")
    service.prepare_hire(second.workspace_id, second.id, discover=lambda kw: market)
    service.execute_hire(second.workspace_id, second.id)
    assert [c[0] for c in calls].count("create-offering-job") == 2


def _mark_funded(record, amount):
    record.fund_state = "funded"
    record.fund_intent = {"idempotency_key": "fund_test", "amount": amount}
    return jobs_mod.put(record)


def test_11_global_pool_exhaustion_blocks_new_spend(policy_env, monkeypatch):
    calls = _bridge_ok(monkeypatch)
    market = [_agent("Cheap", W_A, [_offering("deep_research", RESEARCH_DESC, 0.03)])]
    old = _specified("ws_pol_11old")
    old.status = "accepted"
    _mark_funded(old, 1.00)
    fresh = _specified("ws_pol_11")
    service.prepare_hire(fresh.workspace_id, fresh.id, discover=lambda kw: market)
    with pytest.raises(hiring_mod.HireError, match="temporarily unavailable"):
        service.execute_hire(fresh.workspace_id, fresh.id)
    assert [c[0] for c in calls if c[0] == "create-offering-job"] == []


def test_11b_pool_boundary_exact_fit_allowed(policy_env, monkeypatch):
    _bridge_ok(monkeypatch)
    market = [_agent("Cheap", W_A, [_offering("deep_research", RESEARCH_DESC, 0.03)])]
    old = _specified("ws_pol_11bold")
    old.status = "accepted"
    _mark_funded(old, 0.97)
    fresh = _specified("ws_pol_11b")
    service.prepare_hire(fresh.workspace_id, fresh.id, discover=lambda kw: market)
    service.execute_hire(fresh.workspace_id, fresh.id)


def test_12_over_limit_copy_reaches_api_consumer(policy_env, monkeypatch):
    from prior.marketplace import NoCompatibleProvider

    def _refuse(spec, contract, **kw):
        raise NoCompatibleProvider(
            "This worker costs 2.50 USDC. PRIOR's public safety limit is 0.5 "
            "USDC per job, so nothing was hired and no funds were spent. "
            "Try another available agent.")

    monkeypatch.setattr("prior.marketplace.select_provider_for_spec", _refuse)
    client = TestClient(app)
    client.get("/api/workspace")
    job = client.post("/api/jobs", json={"text": TEXT}).json()
    res = client.post(f"/api/jobs/{job['id']}/hire/prepare")
    assert res.status_code == 400
    body = res.json()["detail"]
    assert "2.50" in body and "0.5" in body
    assert "no funds were spent" in body.lower()
    assert "Try another available agent" in body


def test_13_coingazura_style_003_fixture_remains_eligible(policy_env):
    spec, contract = _query(
        "Review this proposed Base USDC approval before I sign it. "
        "Token: USDC 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913. "
        "Spender 0x1111111111111111111111111111111111111111. Allowance unlimited. "
        "Give an ALLOW, REVIEW, or AVOID verdict with reasoning.")
    market = [_agent("COINGAZURA", W_A, [_offering(
        "coingazura_tx_explain_allow_review_avoid_micro",
        "Transaction safety review for anyone about to sign a wallet transaction. "
        "Verdict ALLOW REVIEW AVOID with risk score for approval popup.",
        0.03,
        requirements={"type": "object", "anyOf": [{"required": ["message"]}],
                      "properties": {"message": {"type": "string"}}},
        deliverable="Plain-language verdict")])]
    sel = select_provider_for_spec(spec, contract, discover=lambda kw: market)
    assert sel.candidate.price_value == 0.03


def test_14_production_defaults_are_050_and_100(monkeypatch):
    import os

    from prior import settings as settings_mod

    monkeypatch.delenv("PRIOR_PUBLIC_MAX_JOB_USDC", raising=False)
    monkeypatch.delenv("PRIOR_PUBLIC_SPEND_LIMIT_USDC", raising=False)
    monkeypatch.delenv("PRIOR_MAX_ACP_JOB_PRICE_USDC", raising=False)
    assert settings_mod.public_max_job_usdc() == 0.50
    assert settings_mod.public_spend_limit_usdc() == 1.00
    assert settings_mod.effective_max_job_usdc() == 0.50
    assert os.getenv("PRIOR_PUBLIC_MAX_JOB_USDC") is None


def test_15_idempotent_execute_still_single_create(policy_env, monkeypatch):
    calls = _bridge_ok(monkeypatch)
    market = [_agent("Cheap", W_A, [_offering("deep_research", RESEARCH_DESC, 0.03)])]
    record = _specified("ws_pol_15")
    service.prepare_hire(record.workspace_id, record.id, discover=lambda kw: market)
    first = service.execute_hire(record.workspace_id, record.id)
    second = service.execute_hire(record.workspace_id, record.id)
    assert first.acp_job_id == second.acp_job_id
    assert [c[0] for c in calls].count("create-offering-job") == 1
