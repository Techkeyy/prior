"""Durable identity: guest -> claim -> cross-device recovery (tests 1-20).

All tests are offline. Google and email providers are stubbed at the
auth-module seam; no external calls, no secrets, no invented success.
"""

from __future__ import annotations

import re
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from prior import auth, jobs
from prior.app import app
from prior.domain import Lesson
from prior.identity import IdentityStore, hash_token
from prior.memory import write_lesson

WS_PATTERN = re.compile(r"^ws_[a-f0-9]{16}$")
GOOGLE_ID = "test-google-client-id"


def make_client() -> TestClient:
    return TestClient(app, base_url="http://testserver")


def guest_ws(client: TestClient) -> str:
    data = client.get("/api/workspace").json()
    assert WS_PATTERN.fullmatch(data["workspace_id"])
    return data["workspace_id"]


def mock_google(monkeypatch, sub="google-sub-1", email="user@example.com", name="User One"):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", GOOGLE_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(
        "prior.auth.google_token_exchange",
        lambda code, uri, verifier: {"id_token": "stub-id-token"},
    )

    def fake_tokeninfo(token):
        assert token == "stub-id-token"
        return {
            "iss": "https://accounts.google.com",
            "aud": GOOGLE_ID,
            "sub": sub,
            "exp": int(time.time()) + 3600,
            "email": email,
            "email_verified": "true",
            "name": name,
        }

    monkeypatch.setattr("prior.auth.google_tokeninfo", fake_tokeninfo)


def google_login(client: TestClient, monkeypatch, **claims) -> dict:
    mock_google(monkeypatch, **claims)
    start = client.get("/api/auth/google/start", follow_redirects=False)
    assert start.status_code in (302, 307)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    done = client.get(
        f"/api/auth/google/callback?code=authcode&state={state}",
        follow_redirects=False,
    )
    assert done.status_code == 302
    assert "signed-in" in done.headers["location"]
    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is True
    return me


def mock_email_code(monkeypatch, code="123456"):
    monkeypatch.setattr("prior.auth._new_email_code", lambda: code)


def email_login(client: TestClient, monkeypatch, email="user@example.com", code="123456") -> dict:
    mock_email_code(monkeypatch, code)
    started = client.post("/api/auth/email/start", json={"email": email}).json()
    assert started["ok"] is True
    done = client.post("/api/auth/email/verify", json={"email": email, "code": code})
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["authenticated"] is True
    return body


def seed_history(client: TestClient, ws: str, acp_job_id: str = "77095") -> tuple[str, str]:
    created = client.post("/api/jobs", json={"text": "Research cloud storage services."}).json()
    record = jobs.get(created["id"], ws)
    assert record is not None
    record.acp_job_id = acp_job_id
    jobs.put(record)
    lesson = Lesson(
        id="les_seed1",
        workspace_id=ws,
        job_type="research",
        issue="seed",
        requirement="Seeded lesson requirement.",
        reason="seeded",
        source_job_id=created["id"],
    )
    write_lesson(ws, lesson)
    return created["id"], lesson.requirement


def jobs_snapshot(client: TestClient) -> list[dict]:
    mem = client.get("/api/memory").json()
    return mem["jobs"]


# 1. anonymous visitor receives isolated workspace
def test_guest_workspaces_are_isolated():
    a, b = make_client(), make_client()
    assert guest_ws(a) != guest_ws(b)


# 2. guest can still use app without signup
def test_guest_can_use_app_without_signup():
    client = make_client()
    ws = guest_ws(client)
    created = client.post("/api/jobs", json={"text": "Research cloud storage services."}).json()
    assert created["workspace_id"] == ws
    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is False
    assert me["workspace_id"] == ws


# 3/4. first Google login claims the guest workspace; ID unchanged
def test_first_google_login_claims_guest_workspace(monkeypatch):
    client = make_client()
    ws = guest_ws(client)
    job_id, requirement = seed_history(client, ws)
    me = google_login(client, monkeypatch)
    assert me["workspace_id"] == ws
    assert me["account"]["email"] == "user@example.com"


# 5. jobs survive claim unchanged
def test_jobs_survive_claim_unchanged(monkeypatch):
    client = make_client()
    ws = guest_ws(client)
    job_id, _ = seed_history(client, ws, acp_job_id="77095")
    before = {j["id"]: j for j in jobs_snapshot(client)}
    google_login(client, monkeypatch)
    after = {j["id"]: j for j in jobs_snapshot(client)}
    assert set(before) == set(after) == {job_id}
    assert after[job_id]["acp_job_id"] == "77095"
    assert after[job_id]["workspace_id"] == ws


# 6. lessons survive claim unchanged
def test_lessons_survive_claim_unchanged(monkeypatch):
    client = make_client()
    ws = guest_ws(client)
    _, requirement = seed_history(client, ws)
    google_login(client, monkeypatch)
    mem = client.get("/api/memory").json()
    assert mem["count"] == 1
    assert mem["lessons"][0]["requirement"] == requirement
    assert mem["lessons"][0]["workspace_id"] == ws


# 7. historical ACP references survive claim unchanged
def test_acp_history_survives_claim_unchanged(monkeypatch):
    client = make_client()
    ws = guest_ws(client)
    job_id, _ = seed_history(client, ws, acp_job_id="77249")
    google_login(client, monkeypatch)
    fetched = client.get(f"/api/jobs/{job_id}").json()
    assert fetched["acp_job_id"] == "77249"
    assert fetched["workspace_id"] == ws


# 8/9. returning account on a new browser resolves the same workspace
def test_returning_account_recovers_same_workspace(monkeypatch):
    first = make_client()
    ws = guest_ws(first)
    seed_history(first, ws)
    google_login(first, monkeypatch)

    second = make_client()
    fresh_guest = guest_ws(second)
    assert fresh_guest != ws
    me = google_login(second, monkeypatch)
    assert me["workspace_id"] == ws
    assert me["workspace_id"] != fresh_guest


# 10. two accounts remain isolated
def test_two_accounts_remain_isolated(monkeypatch):
    a, b = make_client(), make_client()
    me_a = google_login(a, monkeypatch, sub="google-sub-a", email="a@example.com")
    me_b = google_login(b, monkeypatch, sub="google-sub-b", email="b@example.com")
    assert me_a["workspace_id"] != me_b["workspace_id"]


# 11. account A cannot read account B workspace
def test_account_cannot_read_other_workspace(monkeypatch):
    a, b = make_client(), make_client()
    google_login(a, monkeypatch, sub="google-sub-a", email="a@example.com")
    ws_b = guest_ws(b)
    created_b = b.post("/api/jobs", json={"text": "Research cloud storage services."}).json()
    assert created_b["workspace_id"] == ws_b
    denied = a.get(f"/api/jobs/{created_b['id']}")
    assert denied.status_code == 404


# 12. anonymous workspaces remain isolated
def test_anonymous_workspaces_remain_isolated():
    a, b = make_client(), make_client()
    ws_a, ws_b = guest_ws(a), guest_ws(b)
    job_a = a.post("/api/jobs", json={"text": "Research cloud storage services."}).json()
    assert b.get(f"/api/jobs/{job_a['id']}").status_code == 404
    assert ws_a != ws_b


# 13. logout does not delete workspace/memory
def test_logout_preserves_everything(monkeypatch):
    client = make_client()
    ws = guest_ws(client)
    job_id, requirement = seed_history(client, ws)
    google_login(client, monkeypatch)
    assert client.post("/api/auth/logout").json() == {"ok": True}
    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is False
    assert client.get(f"/api/jobs/{job_id}").status_code == 200
    mem = client.get("/api/memory").json()
    assert mem["count"] == 1
    assert mem["lessons"][0]["requirement"] == requirement


# 14. login again restores same workspace
def test_relogin_restores_same_workspace(monkeypatch):
    client = make_client()
    ws = guest_ws(client)
    seed_history(client, ws)
    google_login(client, monkeypatch)
    client.post("/api/auth/logout")
    me = google_login(client, monkeypatch)
    assert me["workspace_id"] == ws


# 15. duplicate login for same provider subject is idempotent
def test_duplicate_login_is_idempotent(monkeypatch):
    from prior import settings as settings_mod

    client = make_client()
    ws = guest_ws(client)
    google_login(client, monkeypatch)
    google_login(client, monkeypatch)
    store = IdentityStore(settings_mod.identity_db_path())
    assert store.count_accounts() == 1
    me = client.get("/api/auth/me").json()
    assert me["workspace_id"] == ws


# 16. different provider subjects do not collide
def test_different_subjects_do_not_collide(monkeypatch):
    a, b = make_client(), make_client()
    me_a = google_login(a, monkeypatch, sub="google-sub-a", email="same@example.com", name="Same Name")
    me_b = google_login(b, monkeypatch, sub="google-sub-b", email="same@example.com", name="Same Name")
    assert me_a["account"]["account_id"] != me_b["account"]["account_id"]
    assert me_a["workspace_id"] != me_b["workspace_id"]


# 17. no automatic merge of returning-account workspace with guest workspace
def test_returning_account_never_auto_merges(monkeypatch):
    first = make_client()
    ws_owned = guest_ws(first)
    seed_history(first, ws_owned)
    google_login(first, monkeypatch)

    second = make_client()
    ws_guest = guest_ws(second)
    guest_job_id, _ = seed_history(second, ws_guest)
    me = google_login(second, monkeypatch)
    assert me["workspace_id"] == ws_owned
    assert me.get("pending_guest_workspace") == ws_guest
    from prior import settings as settings_mod

    store = IdentityStore(settings_mod.identity_db_path())
    assert store.workspace_owner(ws_guest) is None
    assert store.workspace_owner(ws_owned) is not None
    assert store.owned_workspace(me["account"]["account_id"]) == ws_owned
    # Effective view is the owned workspace only; the guest job still exists
    # untouched under its own workspace for a future explicit decision.
    visible = jobs_snapshot(second)
    assert visible and all(j["workspace_id"] == ws_owned for j in visible)
    assert jobs.get(guest_job_id, ws_guest) is not None


# 18. invalid/expired auth session rejected
def test_invalid_and_expired_sessions_rejected(monkeypatch):
    from prior import settings as settings_mod

    client = make_client()
    ws = guest_ws(client)
    client.cookies.set("prior_session", "bogus-token")
    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is False
    assert me["workspace_id"] == ws

    google_login(client, monkeypatch)
    store = IdentityStore(settings_mod.identity_db_path())
    me_now = client.get("/api/auth/me").json()
    account_id = me_now["account"]["account_id"]
    expired = store.create_session(account_id, ttl_s=-1)
    # Simulate a browser holding ONLY the expired session.
    client.cookies.clear()
    client.cookies.set("prior_session", expired, domain="testserver.local")
    me2 = client.get("/api/auth/me").json()
    assert me2["authenticated"] is False


# 19. OAuth state mismatch (and replay) rejected
def test_oauth_state_mismatch_and_replay_rejected(monkeypatch):
    mock_google(monkeypatch)
    client = make_client()
    guest_ws(client)
    bad = client.get(
        "/api/auth/google/callback?code=x&state=not-a-real-state", follow_redirects=False
    )
    assert bad.status_code == 302
    assert "reason=expired" in bad.headers["location"]

    start = client.get("/api/auth/google/start", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    first = client.get(
        f"/api/auth/google/callback?code=x&state={state}", follow_redirects=False
    )
    assert "signed-in" in first.headers["location"]
    replay = client.get(
        f"/api/auth/google/callback?code=x&state={state}", follow_redirects=False
    )
    assert replay.status_code == 302
    assert "reason=expired" in replay.headers["location"]


# 20. provider subject, not display name, controls identity
def test_subject_not_display_name_controls_identity(monkeypatch):
    a, b = make_client(), make_client()
    me_a = google_login(a, monkeypatch, sub="google-sub-a", email="a@example.com", name="Alex")
    me_b = google_login(b, monkeypatch, sub="google-sub-b", email="b@example.com", name="Alex")
    assert me_a["account"]["account_id"] != me_b["account"]["account_id"]


def test_google_start_unconfigured_returns_503():
    client = make_client()
    guest_ws(client)
    resp = client.get("/api/auth/google/start", follow_redirects=False)
    assert resp.status_code == 503
    assert "not configured" in resp.text.lower()


def test_email_otp_claims_workspace_without_delivery(monkeypatch):
    client = make_client()
    ws = guest_ws(client)
    job_id, _ = seed_history(client, ws)
    body = email_login(client, monkeypatch, email="user@example.com")
    assert body["workspace_id"] == ws
    assert body["claimed"] is True
    assert body["provider"] == "email"
    start = client.post("/api/auth/email/start", json={"email": "user@example.com"}).json()
    assert start == {"ok": True, "delivery": "not_configured"}


def test_email_and_google_same_address_do_not_merge(monkeypatch):
    browser = make_client()
    guest_ws(browser)
    email_login(browser, monkeypatch, email="same@example.com")
    acct_email = browser.get("/api/auth/me").json()["account"]["account_id"]
    browser.post("/api/auth/logout")
    google_login(browser, monkeypatch, sub="google-sub-x", email="same@example.com")
    acct_google = browser.get("/api/auth/me").json()["account"]["account_id"]
    assert acct_email != acct_google
