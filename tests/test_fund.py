"""Explicit user-approved funding: prepare/execute with frozen intent.

The bridge is always intercepted here; no live ACP fund occurs. Covers the
25-case funding gate: visibility, read-only paths, frozen intent, safety
refusals, duplicate/ambiguous protection, isolation, and no regressions.
"""

import pytest
from fastapi.testclient import TestClient

from prior import hiring as hiring_mod
from prior import jobs as jobs_mod
from prior import service
from prior.app import app


def _hired(ws, acp_id="77768"):
    record = service.specify(ws, "Research the top five AI wallet companies and compare their features.")
    record.status = "hired"
    record.provider = {
        "id": "0xabc", "name": "ZIZI", "summary": "", "price_label": "0.03",
        "source": "virtuals-acp", "network": "Virtuals ACP",
        "wallet_address": "0xabc", "offering_name": "crypto_news_brief",
    }
    record.acp_job_id = acp_id
    record.acp_phase = "open"
    record.hire_state = "created"
    record.hire_plan = {"idempotency_key": "hire_test", "price_value": 0.03,
                        "contract_fingerprint": hiring_mod.contract_fingerprint(record.contract)}
    return jobs_mod.put(record)


BUDGET = {"amount": "0.03", "symbol": "USDC", "decimals": 6,
          "tokenAddress": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"}


@pytest.fixture
def fund_env(monkeypatch):
    monkeypatch.setenv("ACP_ENABLED", "true")
    monkeypatch.setenv("PRIOR_ENABLE_ACP_WRITES", "true")
    monkeypatch.setenv("BUYER_WALLET_ADDRESS", "0x" + "b0" * 20)
    monkeypatch.setenv("BUYER_WALLET_ID", "buyer-wallet-test")
    monkeypatch.setenv("BUYER_SIGNER_PRIVATE_KEY", "test-signer-key")


@pytest.fixture
def fund_bridge(monkeypatch):
    import time

    import prior.providers.virtuals as virtuals_mod

    calls: list[list] = []
    live_deadline = str(int(time.time()) + 3600)
    status_payload = {"status": {"ok": True, "jobId": "77768", "phase": "open",
                                 "chainId": 8453, "sessionStatus": "open", "hasBudget": True,
                                 "funded": False, "budget": dict(BUDGET),
                                 "expiredAt": live_deadline,
                                 "deliverable": None}}

    def _fake(args):
        calls.append(list(args))
        if args[0] == "status":
            return dict(status_payload["status"])
        if args[0] == "fund":
            return {"ok": True, "jobId": args[1], "action": "fund", "phase": "funded"}
        raise AssertionError(f"unexpected bridge command: {args}")

    monkeypatch.setattr(virtuals_mod, "_bridge", _fake)
    return calls, status_payload


def _prepare(ws, job_id):
    return service.prepare_fund(ws, job_id)


def test_01_budget_set_is_visible_fundable(fund_env, fund_bridge):
    record = _hired("ws_fund_01")
    plan = _prepare("ws_fund_01", record.id)
    assert plan["amount"] == 0.03 and plan["currency"] == "USDC"
    assert plan["agent"] == "ZIZI"


def test_02_status_get_never_funds(fund_env, fund_bridge):
    calls, _ = fund_bridge
    _hired("ws_fund_02")
    job_id = jobs_mod.list_for("ws_fund_02")[0].id
    service.refresh("ws_fund_02", job_id)
    assert [c[0] for c in calls] == ["status"]


def test_03_repeated_status_never_funds(fund_env, fund_bridge):
    calls, _ = fund_bridge
    _hired("ws_fund_03")
    job_id = jobs_mod.list_for("ws_fund_03")[0].id
    for _ in range(10):
        service.refresh("ws_fund_03", job_id)
    assert len(calls) == 10 and {c[0] for c in calls} == {"status"}


def test_04_rendering_fund_ui_never_funds():
    source = open("src/prior/static/app.js", encoding="utf-8").read()
    assert "data-fund\"" in source or "data-fund]" in source
    assert "/fund/prepare" in source and "/fund/execute" in source
    # Render path posts prepare only; execute requires the confirm control.
    assert source.count("fund/execute") == 1


def test_05_fund_prepare_is_read_only(fund_env, fund_bridge):
    calls, _ = fund_bridge
    record = _hired("ws_fund_05")
    _prepare("ws_fund_05", record.id)
    assert {c[0] for c in calls} == {"status"}


def test_06_execute_gate_off_refuses(fund_bridge, monkeypatch):
    monkeypatch.setenv("ACP_ENABLED", "true")
    monkeypatch.setenv("BUYER_WALLET_ADDRESS", "0x" + "b0" * 20)
    monkeypatch.setenv("BUYER_WALLET_ID", "buyer-wallet-test")
    monkeypatch.setenv("BUYER_SIGNER_PRIVATE_KEY", "test-signer-key")
    calls, _ = fund_bridge
    record = _hired("ws_fund_06")
    service.prepare_fund("ws_fund_06", record.id)
    with pytest.raises(hiring_mod.ProviderError) as exc:
        service.execute_fund("ws_fund_06", record.id)
    assert "disabled" in str(exc.value)
    assert [c[0] for c in calls if c[0] == "fund"] == []


def test_07_no_budget_refuses(fund_env, fund_bridge):
    calls, payload = fund_bridge
    payload["status"] = {"ok": True, "jobId": "77768", "phase": "open",
                         "sessionStatus": "open", "hasBudget": False,
                         "funded": False, "budget": None, "deliverable": None}
    record = _hired("ws_fund_07")
    with pytest.raises(hiring_mod.HireError):
        service.prepare_fund("ws_fund_07", record.id)
    assert [c[0] for c in calls if c[0] == "fund"] == []


def test_08_zero_budget_refuses(fund_env, fund_bridge):
    calls, payload = fund_bridge
    payload["status"]["budget"] = dict(BUDGET, amount="0")
    record = _hired("ws_fund_08")
    with pytest.raises(hiring_mod.HireError):
        service.prepare_fund("ws_fund_08", record.id)
    assert [c[0] for c in calls if c[0] == "fund"] == []


def test_09_expired_refuses(fund_env, fund_bridge):
    import time

    calls, payload = fund_bridge
    payload["status"]["expiredAt"] = str(int(time.time()) - 60)
    record = _hired("ws_fund_09")
    with pytest.raises(hiring_mod.HireError):
        service.prepare_fund("ws_fund_09", record.id)
    assert [c[0] for c in calls if c[0] == "fund"] == []


def test_10_unknown_expiry_refuses(fund_env, fund_bridge):
    calls, payload = fund_bridge
    payload["status"].pop("expiredAt", None)
    record = _hired("ws_fund_10")
    with pytest.raises(hiring_mod.HireError):
        service.prepare_fund("ws_fund_10", record.id)
    assert [c[0] for c in calls if c[0] == "fund"] == []


def _live_deadline():
    import time

    return str(int(time.time()) + 3600)


def test_prepare_sets_live_deadline(fund_env, fund_bridge):
    record = _hired("ws_fund_10b")
    record.acp_expired_at = _live_deadline()
    jobs_mod.put(record)
    plan = service.prepare_fund("ws_fund_10b", record.id)
    assert plan["amount"] == 0.03


def test_11_above_approved_price_refuses(fund_env, fund_bridge):
    calls, payload = fund_bridge
    payload["status"]["budget"] = dict(BUDGET, amount="0.05")
    record = _hired("ws_fund_11")
    record.acp_expired_at = _live_deadline()
    jobs_mod.put(record)
    with pytest.raises(hiring_mod.HireError) as exc:
        service.prepare_fund("ws_fund_11", record.id)
    assert "exceeds" in str(exc.value)
    assert [c[0] for c in calls if c[0] == "fund"] == []


def test_12_wrong_currency_refuses(fund_env, fund_bridge):
    calls, payload = fund_bridge
    payload["status"]["budget"] = dict(BUDGET, symbol="USDT",
                                       tokenAddress="0x" + "cc" * 20)
    record = _hired("ws_fund_12")
    record.acp_expired_at = _live_deadline()
    jobs_mod.put(record)
    with pytest.raises(hiring_mod.HireError):
        service.prepare_fund("ws_fund_12", record.id)
    assert [c[0] for c in calls if c[0] == "fund"] == []


def test_13_wrong_chain_refuses(fund_env, fund_bridge, monkeypatch):
    import prior.providers.virtuals as virtuals_mod

    calls, _ = fund_bridge
    real_bridge = virtuals_mod._bridge

    def _wrong_chain(args):
        out = real_bridge(args)
        if args[0] == "status":
            out = dict(out)
            out["chainId"] = 84532
        return out

    monkeypatch.setattr(virtuals_mod, "_bridge", _wrong_chain)
    record = _hired("ws_fund_13")
    with pytest.raises(hiring_mod.HireError) as exc:
        service.prepare_fund("ws_fund_13", record.id)
    assert "8453" in str(exc.value)
    assert [c[0] for c in calls if c[0] == "fund"] == []
    stored = jobs_mod.get(record.id, "ws_fund_13")
    assert stored is not None and stored.fund_state == "fund_failed"


def test_14_wrong_job_mapping_refuses(fund_env, fund_bridge):
    calls, _ = fund_bridge
    record = _hired("ws_fund_14")
    record.acp_expired_at = _live_deadline()
    jobs_mod.put(record)
    service.prepare_fund("ws_fund_14", record.id)
    stored = jobs_mod.get(record.id, "ws_fund_14")
    assert stored is not None and stored.fund_intent is not None
    stored.fund_intent["acp_job_id"] = "99999"
    jobs_mod.put(stored)
    with pytest.raises(hiring_mod.HireError):
        service.execute_fund("ws_fund_14", record.id)
    assert [c[0] for c in calls if c[0] == "fund"] == []


def test_15_cross_workspace_refuses(fund_env, fund_bridge):
    calls, _ = fund_bridge
    record = _hired("ws_fund_15a")
    record.acp_expired_at = _live_deadline()
    jobs_mod.put(record)
    service.prepare_fund("ws_fund_15a", record.id)
    with pytest.raises(KeyError):
        service.execute_fund("ws_fund_15b", record.id)
    with pytest.raises(KeyError):
        service.prepare_fund("ws_fund_15b", record.id)
    assert [c[0] for c in calls if c[0] == "fund"] == []


def test_16_already_funded_cannot_double_fund(fund_env, fund_bridge):
    calls, _ = fund_bridge
    record = _hired("ws_fund_16")
    record.fund_state = "funded"
    jobs_mod.put(record)
    done = service.execute_fund("ws_fund_16", record.id)
    assert done.fund_state == "funded"
    assert [c[0] for c in calls if c[0] == "fund"] == []


def test_17_ambiguous_fund_never_retries(fund_env, monkeypatch):
    import time

    import prior.providers.virtuals as virtuals_mod

    calls: list[list] = []
    live_deadline = str(int(time.time()) + 3600)
    state = {"bridge_done": False}

    def _fake(args):
        calls.append(list(args))
        if args[0] == "status":
            return {"ok": True, "jobId": "77768", "phase": "open",
                    "chainId": 8453, "sessionStatus": "open", "hasBudget": True,
                    "funded": False, "budget": dict(BUDGET),
                    "expiredAt": live_deadline, "deliverable": None}
        if args[0] == "fund":
            state["bridge_done"] = True
            return {"ok": True, "jobId": "77768", "action": "fund", "phase": "funded"}
        raise AssertionError(f"unexpected bridge command: {args}")

    monkeypatch.setattr(virtuals_mod, "_bridge", _fake)
    real_put = jobs_mod.put

    def _flaky_put(record):
        if state["bridge_done"]:
            raise RuntimeError("simulated disk failure after remote fund")
        return real_put(record)

    monkeypatch.setattr(jobs_mod, "put", _flaky_put)
    record = _hired("ws_fund_17")
    record.acp_expired_at = _live_deadline()
    jobs_mod.put(record)
    service.prepare_fund("ws_fund_17", record.id)
    with pytest.raises(hiring_mod.AmbiguousHireError):
        service.execute_fund("ws_fund_17", record.id)
    assert len([c for c in calls if c[0] == "fund"]) == 1
    with pytest.raises(hiring_mod.AmbiguousHireError):
        service.execute_fund("ws_fund_17", record.id)
    assert len([c for c in calls if c[0] == "fund"]) == 1


def test_18_correct_budget_reaches_bridge(fund_env, fund_bridge):
    calls, _ = fund_bridge
    record = _hired("ws_fund_18")
    record.acp_expired_at = _live_deadline()
    jobs_mod.put(record)
    service.prepare_fund("ws_fund_18", record.id)
    done = service.execute_fund("ws_fund_18", record.id)
    assert done.fund_state == "funded"
    funds = [c for c in calls if c[0] == "fund"]
    assert len(funds) == 1 and funds[0][1] == "77768"


def test_19_only_known_bridge_commands(fund_env, fund_bridge):
    calls, _ = fund_bridge
    record = _hired("ws_fund_19")
    record.acp_expired_at = _live_deadline()
    jobs_mod.put(record)
    service.prepare_fund("ws_fund_19", record.id)
    service.execute_fund("ws_fund_19", record.id)
    kinds = {c[0] for c in calls}
    assert kinds <= {"status", "fund"}, kinds
    assert len([c for c in calls if c[0] == "fund"]) == 1


def test_20_budget_revalidated_at_execute(fund_env, fund_bridge):
    calls, payload = fund_bridge
    record = _hired("ws_fund_20")
    record.acp_expired_at = _live_deadline()
    jobs_mod.put(record)
    service.prepare_fund("ws_fund_20", record.id)
    payload["status"]["budget"] = dict(BUDGET, amount="0.09")
    with pytest.raises(hiring_mod.HireError):
        service.execute_fund("ws_fund_20", record.id)
    assert [c[0] for c in calls if c[0] == "fund"] == []


def test_21_hire_paths_unchanged(fund_env, fund_bridge):
    from prior import hiring as hiring_mod

    assert hasattr(hiring_mod, "build_hire_plan")
    assert hasattr(hiring_mod, "validate_preflight")
    calls, _ = fund_bridge
    record = service.specify("ws_fund_21", "Research the top five AI wallet companies.")
    assert record.status == "specified"
    assert [c for c in calls if c[0] in ("create-offering-job", "fund")] == []


def test_22_fund_presentation_shape(fund_env, fund_bridge):
    record = _hired("ws_fund_22")
    record.acp_expired_at = _live_deadline()
    jobs_mod.put(record)
    presentation = service.prepare_fund("ws_fund_22", record.id)
    assert presentation["amount"] == 0.03
    assert presentation["currency"] == "USDC"
    assert presentation["agent"] == "ZIZI"
    assert presentation["acp_job_id"] == "77768"
    assert presentation["idempotency_key"].startswith("fund_")


def test_23_status_read_only_unchanged(fund_env, fund_bridge):
    calls, _ = fund_bridge
    record = _hired("ws_fund_23")
    service.refresh("ws_fund_23", record.id)
    assert {c[0] for c in calls} == {"status"}


def test_24_memory_unchanged():
    from prior import lessons, memory

    assert hasattr(lessons, "applicable_lessons")
    assert hasattr(memory, "recall_lessons")


def test_25_research_engine_has_no_fund_coupling():
    import pathlib

    source = pathlib.Path("src/prior/research.py").read_text(encoding="utf-8")
    for token in ["FundIntent", "fund_claim", "execute_fund", "prepare_fund",
                  "marketplace", "virtuals", "_bridge"]:
        assert token not in source, f"research engine coupled to {token}"


def test_fund_endpoints_reject_without_plan(fund_env, fund_bridge):
    client = TestClient(app)
    ws = client.get("/api/workspace").json()["workspace_id"]
    job = client.post("/api/jobs", json={"text": "Research the top five AI wallet companies."}).json()
    assert client.post(f"/api/jobs/{job['id']}/fund/prepare").status_code == 400
    assert client.post(f"/api/jobs/{job['id']}/fund/execute").status_code == 400
    assert [c for c in fund_bridge[0] if c[0] == "fund"] == []
