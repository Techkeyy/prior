"""Deliverable content transport: the seller's submission must survive every
hop from the ACP history event payload to the JobRecord, and a submission
without content must stay explicitly contentless.

Regression for the ACP 77892 audit: the bridge never read
``event.deliverable`` from the ``job.submitted`` history event (where the
official SDK actually stores the seller's submit() payload for EVM jobs),
and fabricated a placeholder string that PRIOR then presented as the
deliverable while the real content was dropped upstream of Python.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from prior import jobs as jobs_mod
from prior import service

TEXT = "Research the top five AI wallet companies and compare their features."
BRIDGE_DIR = Path("acp-bridge").resolve()

SUBMIT_JSON = json.dumps({
    "offering": "tx_explain",
    "verdict": "AVOID",
    "risk_score": 80,
    "next_step": "do not sign yet",
})


def _acp_record(ws, status="hired", deliverable=None, evaluation=None):
    record = service.specify(ws, TEXT)
    record.status = status
    record.provider = {
        "id": "0xabc", "name": "GAZ", "summary": "", "price_label": "",
        "source": "virtuals-acp", "network": "Virtuals ACP",
        "wallet_address": "0xabc", "offering_name": "tx_explain",
    }
    record.acp_job_id = "77892"
    record.acp_phase = "submitted"
    record.deliverable = deliverable
    record.evaluation = evaluation
    return jobs_mod.put(record)


@pytest.fixture
def bridge(monkeypatch):
    import prior.providers.virtuals as virtuals_mod

    monkeypatch.setenv("ACP_ENABLED", "true")
    monkeypatch.setenv("BUYER_WALLET_ADDRESS", "0x" + "b0" * 20)
    monkeypatch.setenv("BUYER_WALLET_ID", "buyer-wallet-test")
    monkeypatch.setenv("BUYER_SIGNER_PRIVATE_KEY", "test-signer-key")

    calls: list[list] = []
    box = {"payload": {"ok": True, "jobId": "77892", "phase": "submitted",
                       "funded": True, "submitted": True, "deliverable": None}}

    def _fake(args):
        calls.append(list(args))
        assert args[0] == "status", f"read path issued a write: {args}"
        return dict(box["payload"])

    monkeypatch.setattr(virtuals_mod, "_bridge", _fake)
    return calls, box


def test_submitted_event_string_json_survives_as_structured_deliverable(bridge):
    calls, box = bridge
    box["payload"]["deliverable"] = SUBMIT_JSON
    record = _acp_record("ws_dt_01")
    out = service.refresh("ws_dt_01", record.id)
    assert out.status == "delivered"
    assert out.deliverable == {"type": "object", "value": json.loads(SUBMIT_JSON)}
    text = json.dumps(out.deliverable)
    assert "AVOID" in text and "risk_score" in text
    assert "Deliverable confirmed submitted" not in text


def test_submitted_without_content_stays_contentless(bridge):
    calls, box = bridge
    box["payload"]["deliverable"] = None
    record = _acp_record("ws_dt_02")
    out = service.refresh("ws_dt_02", record.id)
    assert out.status == "delivered"
    assert out.deliverable is None
    assert calls and {c[0] for c in calls} == {"status"}


def test_open_phase_without_content_is_not_delivered(bridge):
    calls, box = bridge
    box["payload"].update(phase="open", submitted=False)
    record = _acp_record("ws_dt_03")
    out = service.refresh("ws_dt_03", record.id)
    assert out.status == "hired"
    assert out.deliverable is None


def test_delivered_acp_job_refetches_until_evaluated(bridge):
    calls, box = bridge
    box["payload"]["deliverable"] = SUBMIT_JSON
    record = _acp_record("ws_dt_04")
    first = service.refresh("ws_dt_04", record.id)
    assert first.status == "delivered"
    before = len(calls)
    healed = service.refresh("ws_dt_04", first.id)
    assert len(calls) == before + 1
    assert healed.deliverable is not None


def test_accepted_and_local_delivered_are_not_refetched(bridge):
    calls, box = bridge
    done = _acp_record("ws_dt_05", status="accepted", evaluation="accepted",
                       deliverable={"type": "text", "value": {"text": "x"}})
    before = len(calls)
    service.refresh("ws_dt_05", done.id)
    assert len(calls) == before
    local = service.specify("ws_dt_06", TEXT)
    local.status = "delivered"
    local.provider = {"source": "local-development", "network": "local"}
    local.deliverable = {"type": "text", "value": {"text": "x"}}
    local = jobs_mod.put(local)
    service.refresh("ws_dt_06", local.id)
    assert len(calls) == before


def test_bridge_source_never_fabricates_a_placeholder():
    source = (BRIDGE_DIR / "run.mjs").read_text(encoding="utf-8")
    assert "Deliverable confirmed submitted on-chain by provider." not in source
    assert "extractSubmittedDeliverable(session.entries)" in source
    assert "jobHistoryEntries(rawHistory, jobId)" in source


def _run_node_probe(body: str):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node unavailable")
    probe = BRIDGE_DIR / ".deliverable-probe.mjs"
    probe.write_text(body, encoding="utf-8")
    try:
        proc = subprocess.run([node, str(probe)], cwd=str(BRIDGE_DIR),
                              capture_output=True, text=True, timeout=60)
    finally:
        probe.unlink(missing_ok=True)
    assert proc.returncode == 0, f"probe failed: {proc.stderr[-400:]}"
    return proc.stdout


def test_js_extraction_reads_latest_submitted_event_deliverable():
    out = _run_node_probe(
        "import { extractSubmittedDeliverable, jobHistoryEntries } from './lib.mjs';\n"
        "import assert from 'node:assert';\n"
        "const entries = [\n"
        "  { kind: 'system', event: { type: 'job.submitted', deliverable: 'first' }, onChainJobId: '77892' },\n"
        "  { kind: 'system', event: { type: 'job.submitted', deliverable: '  ' }, onChainJobId: '77892' },\n"
        "  { kind: 'system', event: { type: 'job.submitted', deliverable: '{\"verdict\":\"AVOID\"}' }, onChainJobId: '77892' },\n"
        "];\n"
        "assert.equal(extractSubmittedDeliverable(entries), '{\"verdict\":\"AVOID\"}');\n"
        "assert.equal(extractSubmittedDeliverable([{ kind: 'system', event: { type: 'job.funded' } }]), null);\n"
        "assert.equal(extractSubmittedDeliverable([]), null);\n"
        "const mixed = [\n"
        "  { kind: 'system', event: { type: 'job.submitted', deliverable: 'foreign' }, onChainJobId: '77838' },\n"
        "  { kind: 'system', event: { type: 'job.created' }, onChainJobId: '77892' },\n"
        "];\n"
        "const kept = jobHistoryEntries(mixed, '77892');\n"
        "assert.equal(kept.length, 1);\n"
        "assert.equal(kept[0].event.type, 'job.created');\n"
        "assert.equal(extractSubmittedDeliverable(kept), null);\n"
        "assert.equal(jobHistoryEntries([{ kind: 'message' }, null], '77892').length, 2);\n"
        "console.log('JS-EXTRACTION-OK');\n"
    )
    assert "JS-EXTRACTION-OK" in out
