"""Human quality verdict vs remote marketplace evaluation must be separate.

Regression for the expired-delivery audit (ACP 77892): reject previously
attempted the on-chain evaluation FIRST and only persisted the local verdict
and lesson proposal on success, so an expired (or write-disabled) job could
never record the user's quality decision — and accept/reject were the only
ACP write paths without the PRIOR_ENABLE_ACP_WRITES gate.
"""

import pytest

from prior import jobs as jobs_mod
from prior import service
from prior.providers.virtuals import ProviderError

TEXT = "Research the top five AI wallet companies and compare their features."
REASON = ("The review did not actually use the transaction details that were "
          "provided. It marked the network, token, token address, target and "
          "approval scope as unknown even though those details were present.")


def _delivered(ws, phase="expired", source="virtuals-acp"):
    record = service.specify(ws, TEXT)
    record.status = "delivered"
    record.acp_job_id = "77892"
    record.acp_phase = phase
    record.deliverable = {"type": "object", "value": {"verdict": "AVOID"}}
    record.provider = {
        "id": "0xabc", "name": "GAZ", "summary": "", "price_label": "",
        "source": source, "network": "Virtuals ACP",
        "wallet_address": "0xabc", "offering_name": "tx_explain",
    }
    return jobs_mod.put(record)


@pytest.fixture
def spy_evaluate(monkeypatch):
    calls = []

    def _fake(self, job, accepted, reason):
        calls.append((job.acp_job_id, accepted, reason))
        raise AssertionError("evaluate must not run in this test")

    monkeypatch.setattr("prior.providers.virtuals.VirtualsAcpProvider.evaluate", _fake)
    return calls


def test_expired_job_reject_keeps_verdict_and_lesson(spy_evaluate, monkeypatch):
    monkeypatch.setenv("PRIOR_ENABLE_ACP_WRITES", "true")
    record = _delivered("ws_rt_01")
    out = service.reject("ws_rt_01", record.id, REASON)
    assert out.status == "rejected"
    assert out.evaluation == "rejected"
    assert out.rejection_reason == REASON
    assert out.remote_evaluation == "not attempted (ACP evaluation window expired)"
    assert out.proposed_lesson and out.proposed_lesson["status"] == "proposed"
    assert REASON.split(".")[0] in out.proposed_lesson["requirement"]
    assert spy_evaluate == []


def test_write_gate_blocks_remote_evaluation_for_evaluation_too(monkeypatch):
    monkeypatch.delenv("PRIOR_ENABLE_ACP_WRITES", raising=False)
    calls = []

    def _fake(self, job, accepted, reason):
        calls.append(accepted)
        raise AssertionError("evaluate must not run while writes are disabled")

    monkeypatch.setenv("PRIOR_ENABLE_ACP_WRITES", "false")
    import prior.providers.virtuals as vm
    monkeypatch.setattr(vm.VirtualsAcpProvider, "evaluate", _fake)
    record = _delivered("ws_rt_02", phase="submitted")
    out = service.reject("ws_rt_02", record.id, "Missing sources.")
    assert out.status == "rejected"
    assert out.remote_evaluation == "not attempted (ACP writes disabled by server configuration)"
    assert out.proposed_lesson
    assert calls == []


def test_live_job_reject_confirms_remote_and_stays_truthful(monkeypatch):
    monkeypatch.setenv("PRIOR_ENABLE_ACP_WRITES", "true")
    seen = []

    def _ok(self, job, accepted, reason):
        seen.append((accepted, reason))
        job.phase = "job.rejected"
        return job

    monkeypatch.setattr("prior.providers.virtuals.VirtualsAcpProvider.evaluate", _ok)
    record = _delivered("ws_rt_03", phase="submitted")
    out = service.reject("ws_rt_03", record.id, "Missing sources.")
    assert out.status == "rejected"
    assert out.acp_phase == "job.rejected"
    assert out.remote_evaluation == "confirmed by ACP"
    assert seen == [(False, "Missing sources.")]


def test_remote_failure_records_verdict_without_claiming_success(monkeypatch):
    monkeypatch.setenv("PRIOR_ENABLE_ACP_WRITES", "true")

    def _boom(self, job, accepted, reason):
        raise ProviderError("acp revert: WrongStatus")

    monkeypatch.setattr("prior.providers.virtuals.VirtualsAcpProvider.evaluate", _boom)
    record = _delivered("ws_rt_04", phase="submitted")
    out = service.reject("ws_rt_04", record.id, "Wrong facts.")
    assert out.status == "rejected"
    assert out.proposed_lesson
    assert out.remote_evaluation.startswith("attempt failed:")
    assert "WrongStatus" in out.remote_evaluation
    assert "confirmed" not in out.remote_evaluation


def test_expired_job_accept_keeps_human_verdict(spy_evaluate, monkeypatch):
    monkeypatch.setenv("PRIOR_ENABLE_ACP_WRITES", "true")
    record = _delivered("ws_rt_05")
    out = service.accept("ws_rt_05", record.id)
    assert out.status == "accepted"
    assert out.evaluation == "accepted"
    assert out.remote_evaluation == "not attempted (ACP evaluation window expired)"
    assert spy_evaluate == []


def test_local_reject_flow_unchanged(monkeypatch):
    monkeypatch.setattr("prior.providers.local.run_research",
                        lambda spec, contract: {"type": "object", "value": {"findings": []}}
                        )
    from prior.providers.local import LocalResearchProvider
    monkeypatch.setattr(service, "active_provider", lambda: LocalResearchProvider())
    record = _delivered("ws_rt_06", phase=None, source="local-development")
    out = service.reject("ws_rt_06", record.id, "Generic risk language only.")
    assert out.status == "rejected"
    assert out.remote_evaluation == "confirmed locally"
    assert out.acp_phase == "local.rejected"


def test_lesson_approval_remains_explicit_user_action(spy_evaluate, monkeypatch):
    monkeypatch.setenv("PRIOR_ENABLE_ACP_WRITES", "true")
    from prior.memory import list_lessons
    record = _delivered("ws_rt_07")
    service.reject("ws_rt_07", record.id, REASON)
    assert list_lessons("ws_rt_07") == []
    service.decide_lesson("ws_rt_07", record.id, "add")
    active = list_lessons("ws_rt_07")
    assert len(active) == 1 and active[0].status == "active"


def test_fresh_related_contract_recalls_approved_lesson(spy_evaluate, monkeypatch):
    monkeypatch.setenv("PRIOR_ENABLE_ACP_WRITES", "true")
    record = _delivered("ws_rt_08")
    service.reject("ws_rt_08", record.id,
                   "Use every supplied transaction field including network, token address, "
                   "spender and allowance, and explain the exact permission being granted.")
    service.decide_lesson("ws_rt_08", record.id, "add")
    second = service.specify("ws_rt_08",
                             "Review this proposed Base USDC approval with token address "
                             "0x833589f and spender 0xdEaD before I sign it.")
    assert second.contract.applied_lessons
    assert second.contract.baseline is False
    joined = " ".join(second.contract.acceptance).lower()
    assert "supplied transaction field" in joined


def test_status_stays_read_only_after_verdict(monkeypatch):
    calls = []

    def _fake(self, args):
        calls.append(list(args))
        return {"ok": True, "jobId": "77892", "phase": "expired",
                "funded": True, "submitted": True, "deliverable": None}

    monkeypatch.setenv("ACP_ENABLED", "true")
    monkeypatch.setenv("BUYER_WALLET_ADDRESS", "0x" + "b0" * 20)
    monkeypatch.setenv("BUYER_WALLET_ID", "buyer-wallet-test")
    monkeypatch.setenv("BUYER_SIGNER_PRIVATE_KEY", "test-signer-key")
    import prior.providers.virtuals as vm
    monkeypatch.setattr(vm, "_bridge", _fake)
    record = _delivered("ws_rt_09")
    service.reject("ws_rt_09", record.id, "Generic language only.")
    calls.clear()
    for _ in range(3):
        fresh = jobs_mod.get(record.id, "ws_rt_09")
        service.refresh("ws_rt_09", fresh.id)
    assert all(c[0] == "status" for c in calls)
    again = jobs_mod.get(record.id, "ws_rt_09")
    assert again.status == "rejected"
    assert again.remote_evaluation == "not attempted (ACP writes disabled by server configuration)"


def test_remote_field_round_trips_through_persistence():
    record = _delivered("ws_rt_10")
    record.remote_evaluation = "confirmed by ACP"
    jobs_mod.put(record)
    again = jobs_mod.get(record.id, "ws_rt_10")
    assert again.remote_evaluation == "confirmed by ACP"
    legacy = dict(record.to_dict())
    legacy.pop("remote_evaluation")
    from prior.domain import JobRecord
    assert JobRecord.from_dict(legacy).remote_evaluation is None
