"""Dynamic write-path tests with a strictly intercepted bridge.

No test here contacts the ACP network: prior.providers.virtuals._bridge is
faked, and every fake only answers the read-only `discover` path indirectly
(never used: selection uses injected fixtures) plus the write command
`create-offering-job`. No create-job/fund/complete/reject against a live
system occurs.
"""

import json
import shutil

import pytest

from prior import hiring as hiring_mod
from prior import jobs as jobs_mod
from prior import service
from prior.contract import build_contract
from prior.job_spec import parse_job
from prior.marketplace import NoCompatibleProvider


SELLER_DECOY = "0x" + "de" * 20
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


def _brief_schema(**kw):
    schema = {"type": "object", "required": ["query"],
              "properties": {"query": {"type": "string"}}}
    schema.update(kw)
    return schema


def _market(discover_text="research"):
    return [_agent("Winner Agent", WINNER_WALLET, [
        _offering("deep_research",
                  description="Autonomous research and comparison with reports on any topic.",
                  requirements=_brief_schema())],
        description="Research services.")]


def _discover(market):
    return lambda keyword: market


@pytest.fixture
def acp_env_on(monkeypatch):
    """Satisfy the credentials gate with placeholders; the bridge is always
    intercepted in these tests, so no network is reachable."""
    monkeypatch.setenv("ACP_ENABLED", "true")
    monkeypatch.setenv("BUYER_WALLET_ADDRESS", "0x" + "b0" * 20)
    monkeypatch.setenv("BUYER_WALLET_ID", "buyer-wallet-test")
    monkeypatch.setenv("BUYER_SIGNER_PRIVATE_KEY", "test-signer-key")
    monkeypatch.setenv("SELLER_WALLET_ADDRESS", SELLER_DECOY)


@pytest.fixture
def bridge(monkeypatch):
    import prior.providers.virtuals as virtuals_mod

    calls: list[list] = []
    failures: dict[str, str] = {}

    def _fake(args):
        calls.append(list(args))
        cmd = args[0]
        if cmd in failures:
            raise hiring_mod.ProviderError(failures[cmd])
        if cmd == "create-offering-job":
            return {"ok": True, "jobId": "41234", "phase": "job.created",
                    "chainId": 8453, "providerAddress": args[1],
                    "offeringName": args[2]}
        raise AssertionError(f"unexpected bridge command in write-path test: {args}")

    monkeypatch.setattr(virtuals_mod, "_bridge", _fake)
    return calls, failures


def _job(ws, text="Research the top five AI wallet companies and compare their features."):
    return service.specify(ws, text)


def _fresh(record):
    """Reload the stored record: prepare_hire persists via its own copy."""
    stored = jobs_mod.get(record.id, record.workspace_id)
    assert stored is not None
    return stored


def test_01_selected_provider_becomes_acp_target(acp_env_on, bridge):
    calls, _ = bridge
    record = _job("ws_hire_01")
    plan = service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    assert plan["provider_wallet"] == WINNER_WALLET
    service.execute_hire(record.workspace_id, record.id)
    writes = [c for c in calls if c[0] == "create-offering-job"]
    assert len(writes) == 1 and writes[0][1] == WINNER_WALLET


def test_02_selected_offering_becomes_acp_target(acp_env_on, bridge):
    calls, _ = bridge
    record = _job("ws_hire_02")
    service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    service.execute_hire(record.workspace_id, record.id)
    writes = [c for c in calls if c[0] == "create-offering-job"]
    assert writes[0][2] == "deep_research"


def test_03_no_fixed_seller_substitution(acp_env_on, bridge):
    calls, _ = bridge
    record = _job("ws_hire_03")
    service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    service.execute_hire(record.workspace_id, record.id)
    writes = [c for c in calls if c[0] == "create-offering-job"]
    assert writes[0][1] != SELLER_DECOY
    assert writes[0][1] == WINNER_WALLET


def test_04_learned_clause_survives_to_create_payload(acp_env_on, bridge):
    from prior import memory as memory_mod
    from prior import lessons as lessons_mod
    from prior.domain import Lesson

    calls, _ = bridge
    ws = "ws_hire_04"
    clause = "Include an explicit side-by-side comparison whenever multiple products are requested."
    memory_mod.write_lesson(ws, Lesson(
        id="L1", workspace_id=ws, job_type="research", issue="comparison",
        requirement=clause, reason="write-path gate", status="active",
        created_at=lessons_mod.now_iso()))
    record = service.specify(ws, "Research Base wallet security and compare the leading approaches.")
    assert clause in [lesson.requirement for lesson in record.contract.applied_lessons]
    service.prepare_hire(ws, record.id, discover=_discover(_market()))
    service.execute_hire(ws, record.id)
    writes = [c for c in calls if c[0] == "create-offering-job"]
    assert clause in writes[0][3]


def test_05_requirement_data_survives_structurally(acp_env_on, bridge):
    import prior.jobs as jobs_store

    calls, _ = bridge
    record = _job("ws_hire_05")
    plan = service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    service.execute_hire(record.workspace_id, record.id)
    writes = [c for c in calls if c[0] == "create-offering-job"]
    assert json.loads(writes[0][3]) == plan["requirement_data"]
    stored = jobs_store.get(record.id, record.workspace_id)
    assert stored is not None and stored.worker_requirement == plan["requirement_data"]


def test_06_no_match_creates_no_write(acp_env_on, bridge):
    calls, _ = bridge
    record = _job("ws_hire_06")
    with pytest.raises(NoCompatibleProvider):
        service.prepare_hire(record.workspace_id, record.id, discover=lambda kw: [])
    assert calls == []
    with pytest.raises(ValueError):
        service.execute_hire(record.workspace_id, record.id)
    assert calls == []


def test_07_incompatible_preflight_creates_no_write(acp_env_on, bridge, monkeypatch):
    calls, _ = bridge
    record = _job("ws_hire_07")
    service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    # Contract drift after freezing: preflight K2 must refuse.
    record = _fresh(record)
    record.contract.acceptance.append("Must include emojis in every paragraph.")
    jobs_mod.put(record)
    with pytest.raises(hiring_mod.HireError):
        service.execute_hire(record.workspace_id, record.id)
    assert calls == []
    # Price over the configured max refuses as well.
    monkeypatch.setenv("PRIOR_MAX_ACP_JOB_PRICE_USDC", "0.01")
    record2 = _job("ws_hire_07b")
    service.prepare_hire(record2.workspace_id, record2.id, discover=_discover(_market()))
    with pytest.raises(hiring_mod.HireError):
        service.execute_hire(record2.workspace_id, record2.id)
    assert calls == []


def test_08_required_funds_creates_no_write(acp_env_on, bridge):
    calls, _ = bridge
    record = _job("ws_hire_08")
    plan = service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    plan["required_funds"] = True
    record = _fresh(record)
    record.hire_plan = plan
    jobs_mod.put(record)
    with pytest.raises(hiring_mod.HireError):
        service.execute_hire(record.workspace_id, record.id)
    assert calls == []


def test_09_missing_base_support_creates_no_write(acp_env_on, bridge):
    calls, _ = bridge
    record = _job("ws_hire_09")
    plan = service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    plan["chain_ids"] = [1]
    record = _fresh(record)
    record.hire_plan = plan
    jobs_mod.put(record)
    with pytest.raises(hiring_mod.HireError):
        service.execute_hire(record.workspace_id, record.id)
    assert calls == []


def test_10_contract_loss_preflight_creates_no_write(acp_env_on, bridge):
    calls, _ = bridge
    record = _job("ws_hire_10")
    plan = service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    # Keep the brief slot valid but drop the material requirements: the
    # contract-loss guard must refuse even though schema validation passes.
    plan["requirement_data"] = {"query": "hello"}
    record = _fresh(record)
    record.hire_plan = plan
    jobs_mod.put(record)
    with pytest.raises(hiring_mod.HireError) as exc:
        service.execute_hire(record.workspace_id, record.id)
    assert "not expressible" in str(exc.value)
    assert calls == []


def test_11_double_hire_produces_one_write(acp_env_on, bridge):
    calls, _ = bridge
    record = _job("ws_hire_11")
    service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    first = service.execute_hire(record.workspace_id, record.id)
    second = service.execute_hire(record.workspace_id, record.id)
    assert first.acp_job_id == second.acp_job_id == "41234"
    assert len([c for c in calls if c[0] == "create-offering-job"]) == 1


def test_12_created_job_cannot_create_another(acp_env_on, bridge):
    calls, _ = bridge
    record = _job("ws_hire_12")
    service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    service.execute_hire(record.workspace_id, record.id)
    with pytest.raises(ValueError):
        service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    service.execute_hire(record.workspace_id, record.id)
    assert len([c for c in calls if c[0] == "create-offering-job"]) == 1


def test_13_bridge_failure_leaves_recoverable_state(acp_env_on, bridge):
    calls, failures = bridge
    failures["create-offering-job"] = "simulated ACP outage"
    record = _job("ws_hire_13")
    service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    with pytest.raises(hiring_mod.ProviderError):
        service.execute_hire(record.workspace_id, record.id)
    stored = jobs_mod.get(record.id, record.workspace_id)
    assert stored is not None and stored.hire_state == "failed"
    assert stored.acp_job_id is None and "outage" in (stored.hire_error or "")
    assert len([c for c in calls if c[0] == "create-offering-job"]) == 1
    # Re-prepare after failure is allowed (fresh intent, no write yet).
    plan = service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    assert plan["idempotency_key"]


def test_14_ambiguous_persist_failure_never_retries_blindly(acp_env_on, bridge, monkeypatch):
    calls, _ = bridge
    real_put = jobs_mod.put
    state = {"bridge_done": False, "puts": 0}

    def _flaky_put(record):
        state["puts"] += 1
        if state["bridge_done"] and state["puts"] > 2:
            raise RuntimeError("simulated disk failure after remote create")
        return real_put(record)

    monkeypatch.setattr(jobs_mod, "put", _flaky_put)

    import prior.providers.virtuals as virtuals_mod

    def _fake(args):
        calls.append(list(args))
        assert args[0] == "create-offering-job"
        state["bridge_done"] = True
        return {"ok": True, "jobId": "41234", "phase": "job.created",
                "chainId": 8453, "providerAddress": args[1], "offeringName": args[2]}

    monkeypatch.setattr(virtuals_mod, "_bridge", _fake)
    record = _job("ws_hire_14")
    service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    # puts so far: specify(1) + prepare(1) = 2; creating put = 3rd... recount:
    # specify put, prepare put, creating put, _apply put, final put.
    with pytest.raises(hiring_mod.AmbiguousHireError):
        service.execute_hire(record.workspace_id, record.id)
    creates = [c for c in calls if c[0] == "create-offering-job"]
    assert len(creates) == 1
    with pytest.raises(hiring_mod.AmbiguousHireError):
        service.execute_hire(record.workspace_id, record.id)
    assert len([c for c in calls if c[0] == "create-offering-job"]) == 1


def test_15_workspace_isolation(acp_env_on, bridge):
    calls, _ = bridge
    record = _job("ws_hire_15a")
    service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    with pytest.raises(KeyError):
        service.execute_hire("ws_hire_15b", record.id)
    with pytest.raises(KeyError):
        service.prepare_hire("ws_hire_15b", record.id)
    assert calls == []


def test_16_foreign_plan_cannot_execute(acp_env_on, bridge):
    from prior.providers.virtuals import VirtualsAcpProvider

    calls, _ = bridge
    record = _job("ws_hire_16")
    service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    evil = dict(record.hire_plan or {})
    evil["provider_wallet"] = SELLER_DECOY
    with pytest.raises(hiring_mod.HireError):
        VirtualsAcpProvider().execute_hire(record, evil)
    assert calls == []


def test_17_legacy_path_preserved_not_silent(acp_env_on, bridge, monkeypatch):
    from prior.domain import AgentOffer
    from prior.providers.virtuals import VIRTUALS_SOURCE, VirtualsAcpProvider

    calls, _ = bridge
    legacy = AgentOffer(
        id="legacy", name="Prior Research", summary="legacy seller",
        price_label="", source=VIRTUALS_SOURCE, network="Virtuals ACP",
        wallet_address=SELLER_DECOY, offering_name="research")
    monkeypatch.setattr(
        VirtualsAcpProvider, "find_providers", lambda self, spec: [legacy])

    def _legacy_bridge(args):
        calls.append(list(args))
        assert args[0] == "create-job"
        return {"jobId": "777", "phase": "job.created"}

    import prior.providers.virtuals as virtuals_mod
    monkeypatch.setattr(virtuals_mod, "_bridge", _legacy_bridge)
    record = _job("ws_hire_17")
    started = service.hire(record.workspace_id, record.id)
    assert started.acp_job_id == "777"
    # And the dynamic path refuses an unsatisfiable legacy-shaped market.
    ghost = [_agent("Prior Research", SELLER_DECOY, [
        _offering("research", description="research",
                  requirements={"required": ["unobtainium"]})])]
    record2 = service.specify("ws_hire_17b",
                              "Research the top five AI wallet companies and compare their features.")
    with pytest.raises(NoCompatibleProvider):
        service.prepare_hire(record2.workspace_id, record2.id, discover=_discover(ghost))


def test_18_result_attaches_to_same_logical_job(acp_env_on, bridge):
    calls, _ = bridge
    record = _job("ws_hire_18")
    job_id = record.id
    service.prepare_hire(record.workspace_id, record.id, discover=_discover(_market()))
    done = service.execute_hire(record.workspace_id, record.id)
    assert done.id == job_id
    assert done.status == "hired"
    assert done.acp_job_id == "41234"
    assert (done.provider or {}).get("source") == "virtuals-acp"
    assert (done.provider or {}).get("offering_name") == "deep_research"
    assert done.worker_requirement == done.hire_plan["requirement_data"]
    assert len(jobs_mod.list_for(record.workspace_id)) == 1


def test_sdk_contract_matches_installed_sdk(tmp_path):
    """Our bridge call shape matches the installed SDK's real method.

    Uses inherited stdio plus a result file (this sandbox cannot duplicate
    Windows handles for piped children), the established repo pattern.
    """
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node unavailable")
    import uuid

    bridge_dir = __import__("pathlib").Path("acp-bridge").resolve()
    probe = bridge_dir / f".sdk-probe-{uuid.uuid4().hex}.mjs"
    result = tmp_path / "sdk_probe_result.txt"
    probe.write_text(
        "import { writeFileSync } from 'node:fs';\n"
        "const m = await import('@virtuals-protocol/acp-node-v2');\n"
        "const names = Object.getOwnPropertyNames(m.AcpAgent.prototype);\n"
        "if (!names.includes('createJobByOfferingName')) throw new Error('missing');\n"
        "const fn = m.AcpAgent.prototype.createJobByOfferingName.toString();\n"
        "const head = fn.slice(0, fn.indexOf('{'));\n"
        "for (const param of ['chainId', 'offeringName', 'providerAddress',\n"
        "    'requirementData', 'opts']) {\n"
        "  if (!head.includes(param)) throw new Error('signature drift: ' + param);\n"
        "}\n"
        f"writeFileSync({result.as_posix()!r}, 'SDK_CONTRACT_OK\\n');\n",
        encoding="utf-8",
    )
    # NOTE: stdio inherited, not piped (sandbox WinError 50); result via file.
    last = None
    try:
        for _ in range(3):
            try:
                proc = subprocess.run([node, str(probe)], cwd=str(bridge_dir), timeout=120)
                last = proc
                break
            except OSError as exc:
                last = exc
    finally:
        probe.unlink(missing_ok=True)
    assert not isinstance(last, OSError), f"node spawn failed: {last}"
    assert last.returncode == 0
    assert result.read_text(encoding="utf-8").strip() == "SDK_CONTRACT_OK"
    source = __import__("pathlib").Path("acp-bridge/run.mjs").read_text(encoding="utf-8")
    assert "agent.createJobByOfferingName(" in source
