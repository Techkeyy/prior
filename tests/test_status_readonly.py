"""Status/read paths must be financially inert.

The bridge `status` command previously auto-funded OPEN jobs with a budget.
These tests lock the read-only invariant at three levels: bridge source,
Python bridge-command accounting, and the HTTP/frontend polling paths.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from prior import jobs as jobs_mod
from prior import service
from prior.app import app


def _hired_record(ws, text="Research the top five AI wallet companies and compare their features."):
    record = service.specify(ws, text)
    record.status = "hired"
    record.provider = {
        "id": "0xabc", "name": "ZIZI", "summary": "", "price_label": "",
        "source": "virtuals-acp", "network": "Virtuals ACP",
        "wallet_address": "0xabc", "offering_name": "crypto_news_brief",
    }
    record.acp_job_id = "77768"
    record.acp_phase = "job.created"
    return jobs_mod.put(record)


@pytest.fixture
def status_bridge(monkeypatch):
    import prior.providers.virtuals as virtuals_mod

    monkeypatch.setenv("ACP_ENABLED", "true")
    monkeypatch.setenv("BUYER_WALLET_ADDRESS", "0x" + "b0" * 20)
    monkeypatch.setenv("BUYER_WALLET_ID", "buyer-wallet-test")
    monkeypatch.setenv("BUYER_SIGNER_PRIVATE_KEY", "test-signer-key")

    calls: list[list] = []
    payload = {"status": {"ok": True, "jobId": "77768", "phase": "open",
                          "hasBudget": False, "funded": False, "deliverable": None}}

    def _fake(args):
        calls.append(list(args))
        assert args[0] == "status", f"read path issued a write: {args}"
        return dict(payload["status"])

    monkeypatch.setattr(virtuals_mod, "_bridge", _fake)
    return calls, payload


def _only_status(calls):
    assert calls, "expected bridge status calls"
    assert {c[0] for c in calls} == {"status"}, f"non-read bridge calls: {calls}"


def test_open_with_budget_reports_without_funding(status_bridge):
    calls, payload = status_bridge
    payload["status"] = {"ok": True, "jobId": "77768", "phase": "open",
                         "hasBudget": True, "funded": False,
                         "budget": {"amount": "0.02", "symbol": "USDC", "decimals": 6},
                         "deliverable": None}
    _hired_record("ws_read_01")
    record = service.refresh("ws_read_01", jobs_mod.list_for("ws_read_01")[0].id)
    assert record.acp_phase == "open"
    _only_status(calls)


def test_repeated_status_never_writes(status_bridge):
    calls, _ = status_bridge
    _hired_record("ws_read_02")
    job_id = jobs_mod.list_for("ws_read_02")[0].id
    for _ in range(10):
        service.refresh("ws_read_02", job_id)
    assert len(calls) == 10
    _only_status(calls)


def test_submitted_deliverable_without_writes(status_bridge):
    calls, payload = status_bridge
    payload["status"] = {"ok": True, "jobId": "77768", "phase": "submitted",
                         "hasBudget": True, "funded": True,
                         "deliverable": {"type": "text", "value": {"text": "brief here"}}}
    _hired_record("ws_read_03")
    record = service.refresh("ws_read_03", jobs_mod.list_for("ws_read_03")[0].id)
    assert record.status == "delivered"
    assert record.deliverable is not None
    _only_status(calls)


def test_unknown_job_truthful_no_writes(status_bridge, monkeypatch):
    import prior.providers.virtuals as virtuals_mod

    calls: list[list] = []

    def _boom(args):
        calls.append(list(args))
        raise virtuals_mod.ProviderError("job not found")

    monkeypatch.setattr(virtuals_mod, "_bridge", _boom)
    _hired_record("ws_read_04")
    with pytest.raises(virtuals_mod.ProviderError):
        service.refresh("ws_read_04", jobs_mod.list_for("ws_read_04")[0].id)
    assert [c[0] for c in calls] == ["status"]


def test_explicit_fund_preserved_but_never_called_by_reads():
    bridge = Path("acp-bridge/run.mjs").read_text(encoding="utf-8")
    assert 'if (cmd === "fund")' in bridge
    import re

    for mod, allowed in [
        ("src/prior/service.py", ["execute_fund"]),
        ("src/prior/providers/virtuals.py", ["execute_fund"]),
        ("src/prior/providers/base.py", []),
        ("src/prior/app.py", []),
    ]:
        text = Path(mod).read_text(encoding="utf-8")
        for match in re.finditer(r'\["fund"(?!\w)', text):
            chunk = re.split(r"\n\s*def\s+", text[:match.start()])[-1]
            scope = chunk.split("(")[0].strip()
            assert scope in allowed, f"{mod}: fund bridge call outside {allowed}: in {scope}"


def test_status_command_contains_no_mutation():
    bridge = Path("acp-bridge/run.mjs").read_text(encoding="utf-8")
    start = bridge.index('if (cmd === "status")')
    end = bridge.index('if (cmd === "fund")')
    block = bridge[start:end]
    for forbidden in ["session.fund(", "session.complete(", "session.reject(",
                      "createJob", "sendMessage", "process.exit(1)"]:
        assert forbidden not in block, f"status block contains {forbidden}"


def test_http_get_poll_path_read_only(status_bridge):
    calls, _ = status_bridge
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
    jobs_mod.put(stored)
    for _ in range(3):
        res = client.get(f"/api/jobs/{job['id']}")
        assert res.status_code == 200
    _only_status(calls)


def test_frontend_poll_uses_get_only():
    source = Path("src/prior/static/app.js").read_text(encoding="utf-8")
    start = source.index("async function poll(")
    end = source.index("function escapeHtml(")
    block = source[start:end]
    assert "method" not in block or '"GET"' in block
    assert "POST" not in block
