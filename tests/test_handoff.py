"""One-time workspace handoff: security + UX invariants.

The handoff exists solely for owner UAT on one guest workspace. These tests
lock: opaque tokens (no workspace id in the URL), single use, expiry,
unforgeability of other-workspace selection, cookie parity with the normal
guest path, and zero side effects on ACP/jobs/lessons/ownership.
"""

import json
import time

import pytest
from fastapi.testclient import TestClient

from prior import handoff
from prior import jobs as jobs_mod
from prior import service
from prior.app import app

TARGET = "ws_" + "ab" * 8
OTHER = "ws_" + "cd" * 8
TEXT = "Research the top five AI wallet companies and compare their features."


def _client() -> TestClient:
    return TestClient(app)


def test_valid_token_sets_bound_workspace_and_redirects():
    client = _client()
    owner = _client()
    owner.post("/api/jobs", json={"text": TEXT})
    ws = owner.cookies.get("prior_workspace")
    assert ws
    job = owner.post("/api/jobs", json={"text": TEXT}).json()
    token = handoff.issue(ws)
    assert token and ws not in token
    res = client.get(f"/handoff/{token}", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/app"
    cookie = res.headers["set-cookie"]
    assert f"prior_workspace={ws}" in cookie
    assert "httponly" in cookie.lower() and "samesite=lax" in cookie.lower()
    mine = client.get("/api/jobs/" + job["id"])
    assert mine.status_code == 200
    assert mine.json()["workspace_id"] == ws


def test_second_use_fails_and_is_identical_to_random():
    client = _client()
    token = handoff.issue(TARGET)
    ok = client.get(f"/handoff/{token}", follow_redirects=False)
    assert ok.status_code == 302
    stale = _client().get(f"/handoff/{token}", follow_redirects=False)
    bogus = _client().get("/handoff/" + "x" * 60, follow_redirects=False)
    assert stale.status_code == bogus.status_code == 404
    assert "prior_workspace" not in stale.headers.get("set-cookie", "")


def test_expired_token_fails():
    token = handoff.issue(TARGET, ttl_s=30)
    path = handoff.settings.handoff_path()
    store = json.loads(path.read_text(encoding="utf-8"))
    store["tokens"][token]["exp"] = int(time.time()) - 1
    path.write_text(json.dumps(store), encoding="utf-8")
    res = _client().get(f"/handoff/{token}", follow_redirects=False)
    assert res.status_code == 404


def test_url_editing_cannot_switch_workspaces():
    token_a = handoff.issue(TARGET)
    token_b = handoff.issue(OTHER)
    client = _client()
    client.get(f"/handoff/{token_a}", follow_redirects=False)
    assert client.cookies.get("prior_workspace") == TARGET
    swapped = client.get(f"/handoff/{token_a}%2F..%2F{OTHER}", follow_redirects=False)
    assert swapped.status_code == 404
    fresh = _client()
    fresh.get(f"/handoff/{token_b}", follow_redirects=False)
    assert fresh.cookies.get("prior_workspace") == OTHER
    probe = _client()
    probe.get(f"/handoff/{token_b[:-2]}xx", follow_redirects=False)
    assert probe.cookies.get("prior_workspace") is None


def test_account_owned_workspace_is_refused(monkeypatch):
    token = handoff.issue(TARGET)
    from prior import auth

    class _Owned:
        def workspace_owner(self, ws):
            return "acct_1" if ws == TARGET else None

    monkeypatch.setattr(auth, "get_store", lambda: _Owned())
    res = _client().get(f"/handoff/{token}", follow_redirects=False)
    assert res.status_code == 404
    assert "prior_workspace" not in res.headers.get("set-cookie", "")


def test_handoff_performs_no_acp_calls_and_mutates_nothing(monkeypatch):
    import prior.providers.virtuals as vm

    def _boom(args):
        raise AssertionError(f"handoff must never touch the ACP bridge: {args}")

    monkeypatch.setattr(vm, "_bridge", _boom)
    client = _client()
    client.post("/api/jobs", json={"text": TEXT})
    ws = client.cookies.get("prior_workspace")
    record = service.specify(ws, TEXT)
    before = jobs_mod.get(record.id, ws).to_dict()
    token = handoff.issue(ws)
    res = client.get(f"/handoff/{token}", follow_redirects=False)
    assert res.status_code == 302
    assert jobs_mod.get(record.id, ws).to_dict() == before
    assert handoff.issue("not-a-workspace") is None


def test_guest_and_auth_paths_unchanged_by_route():
    client = _client()
    first = client.get("/api/workspace").json()["workspace_id"]
    again = client.get("/api/workspace").json()["workspace_id"]
    assert first == again
    assert handoff.redeem("") is None
    assert handoff.redeem("a.b") is None
    assert handoff.remaining_ttl("nope") is None
