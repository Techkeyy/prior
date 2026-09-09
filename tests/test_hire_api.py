"""Hire prepare/execute API contract, concurrency, freshness, and drift.

Uses FastAPI TestClient (isolated stores via conftest) and an intercepted
bridge. No live ACP calls. Covers the user-shaped end-to-end flow through
the REAL application endpoints.
"""

import json
import threading

import pytest
from fastapi.testclient import TestClient

from prior import hiring as hiring_mod
from prior import jobs as jobs_mod
from prior import service
from prior.app import app


WINNER_WALLET = "0x" + "aa" * 20


def _agent(name, wallet, offerings, **kw):
    return {
        "id": f"id-{name}", "name": name,
        "description": kw.get("description", ""),
        "walletAddress": wallet,
        "lastActiveAt": kw.get("lastActiveAt", "2026-09-01T00:00:00Z"),
        "rating": kw.get("rating", 4.0), "isHidden": kw.get("isHidden", False),
        "chains": kw.get("chains", [{"chainId": 8453}]),
        "offerings": offerings,
    }


def _offering(name, **kw):
    return {
        "name": name,
        "description": kw.get("description", ""),
        "requirements": kw.get("requirements", {}),
        "deliverable": kw.get("deliverable", ""),
        "priceType": kw.get("priceType", "fixed"),
        "priceValue": kw.get("priceValue", 0.5),
        "requiredFunds": kw.get("requiredFunds", False),
        "slaMinutes": kw.get("slaMinutes", 10),
        "isHidden": kw.get("isHidden", False),
        "isPrivate": kw.get("isPrivate", False),
    }


def _market():
    return [_agent("Winner Agent", WINNER_WALLET, [
        _offering("deep_research",
                  description="Autonomous research and comparison with reports on any topic.",
                  requirements={"type": "object", "required": ["query"],
                                "properties": {"query": {"type": "string"}}})],
        description="Research services.")]


def _refresh_ok(args):
    name = args[2] if len(args) > 2 else "deep_research"
    return {"ok": True, "found": True, "chainId": 8453,
            "agentName": "Winner Agent",
            "walletAddress": args[1] if len(args) > 1 else WINNER_WALLET,
            "chains": [8453],
            "offering": {
                "name": name,
                "description": "Autonomous research and comparison with reports on any topic.",
                "requirements": {"type": "object", "required": ["query"],
                                 "properties": {"query": {"type": "string"}}},
                "priceType": "fixed", "priceValue": 0.5,
                "requiredFunds": False, "isHidden": False, "isPrivate": False}}


@pytest.fixture
def api_env(monkeypatch):
    monkeypatch.setenv("ACP_ENABLED", "true")
    monkeypatch.setenv("PRIOR_ENABLE_ACP_WRITES", "true")
    monkeypatch.setenv("BUYER_WALLET_ADDRESS", "0x" + "b0" * 20)
    monkeypatch.setenv("BUYER_WALLET_ID", "buyer-wallet-test")
    monkeypatch.setenv("BUYER_SIGNER_PRIVATE_KEY", "test-signer-key")


@pytest.fixture
def api_bridge(monkeypatch):
    import prior.providers.virtuals as virtuals_mod

    calls: list[list] = []

    def _fake(args):
        calls.append(list(args))
        if args[0] == "offering-refresh":
            return _refresh_ok(args)
        if args[0] == "create-offering-job":
            return {"ok": True, "jobId": "41234", "phase": "job.created",
                    "chainId": 8453, "providerAddress": args[1],
                    "offeringName": args[2]}
        raise AssertionError(f"unexpected bridge command: {args}")

    monkeypatch.setattr(virtuals_mod, "_bridge", _fake)
    return calls


@pytest.fixture
def api_select(monkeypatch):
    import prior.marketplace as marketplace_mod

    real_select = marketplace_mod.select_provider_for_spec

    def _select(spec, contract, discover=None):
        return real_select(spec, contract, discover=lambda kw: _market())

    monkeypatch.setattr(marketplace_mod, "select_provider_for_spec", _select)
    # service imported select_provider_for_spec indirectly via provider; the
    # provider calls marketplace.select_provider_for_spec at call time.
    import prior.providers.virtuals as virtuals_mod  # noqa: F401


def _client():
    return TestClient(app)


def test_prepare_endpoint_returns_confirmation(api_env, api_bridge, api_select):
    client = _client()
    job = client.post("/api/jobs", json={
        "text": "Research the top five AI wallet companies and compare their features."}).json()
    res = client.post(f"/api/jobs/{job['id']}/hire/prepare")
    assert res.status_code == 200, res.text
    body = res.json()
    plan = body["hire_plan"]
    assert plan["agent"] == "Winner Agent"
    assert plan["offering"] == "deep_research"
    assert plan["network"] == "Virtuals ACP"
    assert plan["price"] == "0.5 USDC"
    assert plan["remembered"] == []
    assert "query" in plan["requirement_data"]
    assert body["job"]["hire_state"] == "prepared"


def test_prepare_no_match_is_truthful(api_env, api_bridge, api_select, monkeypatch):
    import prior.marketplace as marketplace_mod
    from prior.marketplace import NoCompatibleProvider

    def _none(spec, contract, discover=None):
        raise NoCompatibleProvider("No compatible Virtuals agent was found for this job.")

    monkeypatch.setattr(marketplace_mod, "select_provider_for_spec", _none)
    client = _client()
    job = client.post("/api/jobs", json={"text": "Research the top five AI wallet companies."}).json()
    res = client.post(f"/api/jobs/{job['id']}/hire/prepare")
    assert res.status_code == 400
    assert "No compatible" in res.json()["detail"]


def test_execute_refuses_when_gate_off(api_bridge, api_select, monkeypatch):
    monkeypatch.setenv("ACP_ENABLED", "true")
    monkeypatch.setenv("BUYER_WALLET_ADDRESS", "0x" + "b0" * 20)
    monkeypatch.setenv("BUYER_WALLET_ID", "buyer-wallet-test")
    monkeypatch.setenv("BUYER_SIGNER_PRIVATE_KEY", "test-signer-key")
    # PRIOR_ENABLE_ACP_WRITES intentionally left OFF.
    client = _client()
    job = client.post("/api/jobs", json={"text": "Research the top five AI wallet companies."}).json()
    assert client.post(f"/api/jobs/{job['id']}/hire/prepare").status_code == 200
    res = client.post(f"/api/jobs/{job['id']}/hire/execute")
    assert res.status_code == 403
    assert [c for c in api_bridge if c[0] == "create-offering-job"] == []


def test_execute_end_to_end_intercepted(api_env, api_bridge, api_select):
    client = _client()
    job = client.post("/api/jobs", json={"text": "Research the top five AI wallet companies."}).json()
    client.post(f"/api/jobs/{job['id']}/hire/prepare")
    res = client.post(f"/api/jobs/{job['id']}/hire/execute")
    assert res.status_code == 200, res.text
    done = res.json()
    assert done["status"] == "hired" and done["acp_job_id"] == "41234"
    assert (done["provider"] or {}).get("offering_name") == "deep_research"
    writes = [c for c in api_bridge if c[0] == "create-offering-job"]
    assert len(writes) == 1 and writes[0][1] == WINNER_WALLET
    assert writes[0][2] == "deep_research"


def test_normal_ui_never_calls_legacy_hire():
    from pathlib import Path

    source = Path("src/prior/static/app.js").read_text(encoding="utf-8")
    assert "/hire/prepare" in source and "/hire/execute" in source
    import re

    legacy_calls = re.findall(r"/hire`", source)
    assert legacy_calls == [], f"frontend still calls legacy hire endpoint: {legacy_calls}"


def test_legacy_service_hire_not_used_by_new_endpoints(api_env, api_bridge, api_select, monkeypatch):
    import prior.service as service_mod

    def _boom(*args, **kwargs):
        raise AssertionError("normal UI path reached legacy service.hire")

    monkeypatch.setattr(service_mod, "hire", _boom)
    client = _client()
    job = client.post("/api/jobs", json={"text": "Research the top five AI wallet companies."}).json()
    assert client.post(f"/api/jobs/{job['id']}/hire/prepare").status_code == 200
    assert client.post(f"/api/jobs/{job['id']}/hire/execute").status_code == 200


def test_memory_clause_reaches_intercepted_create(api_env, api_bridge, api_select):
    from prior import lessons as lessons_mod
    from prior import memory as memory_mod
    from prior.domain import Lesson

    client = _client()
    ws = client.get("/api/workspace").json()["workspace_id"]
    clause = "Include an explicit side-by-side comparison whenever multiple products are requested."
    memory_mod.write_lesson(ws, Lesson(
        id="L1", workspace_id=ws, job_type="research", issue="comparison",
        requirement=clause, reason="api gate", status="active",
        created_at=lessons_mod.now_iso()))
    job = client.post("/api/jobs", json={
        "text": "Research Base wallet security practices and compare the leading approaches."}).json()
    assert clause in [lesson["requirement"] for lesson in job["contract"]["applied_lessons"]]
    body = client.post(f"/api/jobs/{job['id']}/hire/prepare").json()
    assert clause in body["hire_plan"]["remembered"]
    assert client.post(f"/api/jobs/{job['id']}/hire/execute").status_code == 200
    writes = [c for c in api_bridge if c[0] == "create-offering-job"]
    payload = json.loads(writes[0][3])
    blob = " ".join(str(v) for v in payload.values() if isinstance(v, str))
    assert clause in blob


def test_concurrent_execute_produces_one_write(api_env, monkeypatch):
    import time

    import prior.providers.virtuals as virtuals_mod

    calls: list[list] = []
    barrier = threading.Barrier(2)

    def _slow_bridge(args):
        calls.append(list(args))
        if args[0] == "offering-refresh":
            return _refresh_ok(args)
        assert args[0] == "create-offering-job"
        time.sleep(0.5)
        return {"ok": True, "jobId": "41234", "phase": "job.created",
                "chainId": 8453, "providerAddress": args[1], "offeringName": args[2]}

    monkeypatch.setattr(virtuals_mod, "_bridge", _slow_bridge)
    record = service.specify("ws_race", "Research the top five AI wallet companies and compare their features.")
    service.prepare_hire("ws_race", record.id,
                         discover=lambda kw: _market())
    outcomes: list[str] = []

    def _run():
        # Maximize the collision window: both threads enter execute together.
        barrier.wait(timeout=30)
        try:
            done = service.execute_hire("ws_race", record.id)
            outcomes.append(f"ok:{done.acp_job_id}")
        except Exception as exc:  # noqa: BLE001 - both outcomes acceptable, never a 2nd write
            outcomes.append(f"refused:{type(exc).__name__}")

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert len([c for c in calls if c[0] == "create-offering-job"]) == 1
    assert len(outcomes) == 2
    final = jobs_mod.get(record.id, "ws_race")
    assert final is not None and final.acp_job_id == "41234" and final.hire_state == "created"


def test_two_jobs_execute_independently(api_env, monkeypatch):
    import prior.providers.virtuals as virtuals_mod

    calls: list[list] = []

    def _fake(args):
        calls.append(list(args))
        if args[0] == "offering-refresh":
            return _refresh_ok(args)
        return {"ok": True, "jobId": f"job-{args[1][-4:]}", "phase": "job.created",
                "chainId": 8453, "providerAddress": args[1], "offeringName": args[2]}

    monkeypatch.setattr(virtuals_mod, "_bridge", _fake)
    ids = []
    for index, wallet in enumerate(["0x" + "aa" * 20, "0x" + "bb" * 20]):
        market = [_agent("Winner Agent", wallet, [
            _offering("deep_research",
                      description="Autonomous research and comparison with reports on any topic.",
                      requirements={"type": "object", "required": ["query"],
                                    "properties": {"query": {"type": "string"}}})])]
        record = service.specify(f"ws_parallel_{index}",
                                 f"Research topic number {index} and compare the leading options.")
        service.prepare_hire(f"ws_parallel_{index}", record.id, discover=lambda kw: market)
        done = service.execute_hire(f"ws_parallel_{index}", record.id)
        ids.append(done.acp_job_id)
    assert len([c for c in calls if c[0] == "create-offering-job"]) == 2
    assert ids[0] != ids[1]


def test_restart_keeps_ambiguous_refusal(api_env, api_bridge):
    calls = api_bridge
    record = service.specify("ws_restart", "Research the top five AI wallet companies and compare their features.")
    service.prepare_hire("ws_restart", record.id, discover=lambda kw: _market())
    stored = jobs_mod.get(record.id, "ws_restart")
    assert stored is not None
    stored.hire_state = "ambiguous"
    stored.hire_error = "simulated pre-restart ambiguity"
    jobs_mod.put(stored)
    hiring_mod._COMPLETED_WRITES.clear()
    hiring_mod._AMBIGUOUS_JOBS.clear()
    with pytest.raises(hiring_mod.AmbiguousHireError):
        service.execute_hire("ws_restart", record.id)
    assert [c for c in calls if c[0] == "create-offering-job"] == []


def test_freshness_price_drift_refuses(api_env, api_select, monkeypatch):
    import prior.providers.virtuals as virtuals_mod

    calls: list[list] = []

    def _drifted(args):
        calls.append(list(args))
        assert args[0] == "offering-refresh"
        out = _refresh_ok(args)
        out["offering"] = dict(out["offering"])
        out["offering"]["priceValue"] = 50.0
        return out

    monkeypatch.setattr(virtuals_mod, "_bridge", _drifted)
    record = service.specify("ws_drift", "Research the top five AI wallet companies and compare their features.")
    service.prepare_hire("ws_drift", record.id, discover=lambda kw: _market())
    with pytest.raises(hiring_mod.HireError) as exc:
        service.execute_hire("ws_drift", record.id)
    assert "changed" in str(exc.value) or "cap" in str(exc.value)
    assert [c for c in calls if c[0] == "create-offering-job"] == []
    stored = jobs_mod.get(record.id, "ws_drift")
    assert stored is not None and stored.hire_state == "failed"


def test_verify_freshness_unit_cases():
    import copy

    from prior.job_spec import parse_job
    from prior.contract import build_contract
    from prior.hiring import HirePlan, verify_freshness
    from prior.marketplace import build_capability_query

    spec = parse_job("Research the top five AI wallet companies.")
    contract = build_contract(spec, [])
    query = build_capability_query(spec, contract)
    base = {"found": True,
            "offering": {"name": "r", "description": "research",
                         "requirements": {"type": "object", "required": ["query"],
                                          "properties": {"query": {"type": "string"}}},
                         "priceType": "fixed", "priceValue": 0.5,
                         "requiredFunds": False, "isHidden": False, "isPrivate": False},
            "chains": [8453]}
    from prior.hiring import HirePlan, verify_freshness

    def _plan(**over):
        data = {"idempotency_key": "k", "workspace_id": "w", "logical_job_id": "j",
                "provider_wallet": "0xabc", "offering_name": "r",
                "chain_ids": [8453], "price_type": "fixed", "price_value": 0.5,
                "required_funds": False,
                "requirements_schema": base["offering"]["requirements"],
                "requirement_data": {"query": "brief"},
                "contract_fingerprint": "x"}
        data.update(over)
        return HirePlan.from_dict(data)

    assert verify_freshness(
        type("R", (), {"workspace_id": "w", "id": "j", "contract": contract})(),
        _plan(), copy.deepcopy(base)) == []
    changed = copy.deepcopy(base)
    changed["offering"]["priceValue"] = 99.0
    assert hiring_mod.verify_freshness(
        type("R", (), {"workspace_id": "w", "id": "j", "contract": contract})(),
        _plan(), changed) != []
    hidden = copy.deepcopy(base)
    hidden["offering"]["isHidden"] = True
    assert hiring_mod.verify_freshness(
        type("R", (), {"workspace_id": "w", "id": "j", "contract": contract})(),
        _plan(), hidden) != []
