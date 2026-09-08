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


def mock_google(
    monkeypatch,
    sub="google-sub-1",
    email="user@example.com",
    name="User One",
    *,
    nonce_mode: str = "captured",
    iss: str = "https://accounts.google.com",
    aud: str | None = None,
    exp_offset: int = 3600,
    include_sub: bool = True,
):
    """nonce_mode: captured (use the authorization nonce), omit, or a literal wrong value."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", GOOGLE_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    captured = {"nonce": None, "verifier": None}

    def fake_exchange(code, uri, verifier):
        captured["verifier"] = verifier
        assert verifier, "PKCE verifier must be sent on the token exchange"
        return {"id_token": "stub-id-token"}

    monkeypatch.setattr("prior.auth.google_token_exchange", fake_exchange)

    def fake_verify(token):
        assert token == "stub-id-token"
        info = {
            "iss": iss,
            "aud": GOOGLE_ID if aud is None else aud,
            "exp": int(time.time()) + exp_offset,
            "email": email,
            "email_verified": "true",
            "name": name,
        }
        if include_sub:
            info["sub"] = sub
        if nonce_mode == "captured":
            info["nonce"] = captured["nonce"]
        elif nonce_mode == "omit":
            pass
        else:
            info["nonce"] = nonce_mode
        return info

    # Production path uses verify_google_id_token (google-auth library);
    # google_tokeninfo remains as a deprecated alias.
    monkeypatch.setattr("prior.auth.verify_google_id_token", fake_verify)
    monkeypatch.setattr("prior.auth.google_tokeninfo", fake_verify)
    return captured


def google_callback(client: TestClient, monkeypatch, *, follow_redirects=False, **claims):
    """Run one Google start->callback round with controllable claims.

    Returns (callback_response, captured). Raises nothing; caller asserts
    on the redirect location.
    """
    captured = mock_google(monkeypatch, **claims)
    start = client.get("/api/auth/google/start", follow_redirects=False)
    assert start.status_code in (302, 307)
    qs = parse_qs(urlparse(start.headers["location"]).query)
    captured["nonce"] = qs["nonce"][0]
    state = qs["state"][0]
    done = client.get(
        f"/api/auth/google/callback?code=authcode&state={state}",
        follow_redirects=follow_redirects,
    )
    return done, captured


def google_login(client: TestClient, monkeypatch, **claims) -> dict:
    captured = mock_google(monkeypatch, **claims)
    start = client.get("/api/auth/google/start", follow_redirects=False)
    assert start.status_code in (302, 307)
    qs = parse_qs(urlparse(start.headers["location"]).query)
    assert qs.get("code_challenge") and qs.get("code_challenge_method") == ["S256"]
    assert qs.get("nonce") and qs.get("state")
    captured["nonce"] = qs["nonce"][0]
    state = qs["state"][0]
    done = client.get(
        f"/api/auth/google/callback?code=authcode&state={state}",
        follow_redirects=False,
    )
    assert done.status_code == 302
    assert "signed-in" in done.headers["location"]
    assert "prior_session=" in (done.headers.get("set-cookie") or "")
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


# 13. logout preserves data server-side but denies anonymous access to owned WS
def test_logout_preserves_data_but_denies_anonymous_access(monkeypatch):
    from prior import settings as settings_mod

    client = make_client()
    ws = guest_ws(client)
    job_id, requirement = seed_history(client, ws)
    google_login(client, monkeypatch)
    store = IdentityStore(settings_mod.identity_db_path())
    assert store.workspace_owner(ws) is not None
    assert client.post("/api/auth/logout").json() == {"ok": True}
    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is False
    # Owned workspace must NOT resolve anonymously: safe guest issued.
    assert me["workspace_id"] != ws
    assert WS_PATTERN.fullmatch(me["workspace_id"])
    # Direct owned-job GET denied after logout.
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    # Owned memory not exposed after logout.
    mem = client.get("/api/memory").json()
    assert mem["count"] == 0
    assert all(l["workspace_id"] != ws for l in mem["lessons"])
    # Data itself is preserved server-side (owner can get it back).
    assert jobs.get(job_id, ws) is not None


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

    # Manual round so the stubbed verifier echoes the real authorization nonce.
    captured = mock_google(monkeypatch)
    start = client.get("/api/auth/google/start", follow_redirects=False)
    qs = parse_qs(urlparse(start.headers["location"]).query)
    captured["nonce"] = qs["nonce"][0]
    state = qs["state"][0]
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


def test_google_start_unconfigured_returns_503(monkeypatch):
    # Pin the precondition: developer .env may hold real Google creds.
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
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


# ---- security gate: owned workspace anonymous denial ----

def test_safe_guest_issued_after_logout(monkeypatch):
    from prior import settings as settings_mod

    client = make_client()
    ws = guest_ws(client)
    seed_history(client, ws)
    google_login(client, monkeypatch)
    client.post("/api/auth/logout")
    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is False
    assert me["workspace_id"] != ws
    assert WS_PATTERN.fullmatch(me["workspace_id"])
    store = IdentityStore(settings_mod.identity_db_path())
    assert store.workspace_owner(me["workspace_id"]) is None


def test_stale_copied_owned_cookie_cannot_access(monkeypatch):
    owner = make_client()
    ws = guest_ws(owner)
    job_id, _ = seed_history(owner, ws)
    google_login(owner, monkeypatch)

    thief = make_client()
    guest_ws(thief)
    # Attacker copies the stale pre-claim workspace cookie value.
    thief.cookies.set("prior_workspace", ws)
    me = thief.get("/api/auth/me").json()
    assert me["authenticated"] is False
    assert me["workspace_id"] != ws
    assert thief.get(f"/api/jobs/{job_id}").status_code == 404
    mem = thief.get("/api/memory").json()
    assert mem["count"] == 0


def test_invalid_session_plus_owned_cookie_denied(monkeypatch):
    client = make_client()
    ws = guest_ws(client)
    job_id, _ = seed_history(client, ws)
    google_login(client, monkeypatch)
    client.post("/api/auth/logout")
    # Browser retains/copies owned workspace cookie with a bogus session.
    client.cookies.set("prior_session", "bogus-token")
    client.cookies.set("prior_workspace", ws)
    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is False
    assert me["workspace_id"] != ws
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_expired_session_plus_owned_cookie_denied(monkeypatch):
    from prior import settings as settings_mod

    client = make_client()
    ws = guest_ws(client)
    job_id, _ = seed_history(client, ws)
    google_login(client, monkeypatch)
    me_now = client.get("/api/auth/me").json()
    account_id = me_now["account"]["account_id"]
    store = IdentityStore(settings_mod.identity_db_path())
    expired = store.create_session(account_id, ttl_s=-1)
    client.post("/api/auth/logout")
    client.cookies.set("prior_session", expired)
    client.cookies.set("prior_workspace", ws)
    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is False
    assert me["workspace_id"] != ws
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_logout_revokes_actual_server_session(monkeypatch):
    from prior import settings as settings_mod

    client = make_client()
    guest_ws(client)
    google_login(client, monkeypatch)
    raw_cookie = client.cookies.get("prior_session")
    assert raw_cookie
    store = IdentityStore(settings_mod.identity_db_path())
    assert store.lookup_session(raw_cookie) is not None
    client.post("/api/auth/logout")
    assert store.lookup_session(raw_cookie) is None
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_returning_account_preserves_guest_across_logout(monkeypatch):
    first = make_client()
    ws_owned = guest_ws(first)
    seed_history(first, ws_owned)
    google_login(first, monkeypatch)

    second = make_client()
    ws_guest = guest_ws(second)
    guest_job = second.post("/api/jobs", json={"text": "Research cloud storage services."}).json()
    assert guest_job["workspace_id"] == ws_guest
    me = google_login(second, monkeypatch)
    assert me["workspace_id"] == ws_owned
    # While signed in, the unrelated guest cookie is preserved, not merged.
    assert second.cookies.get("prior_workspace") == ws_guest
    second.post("/api/auth/logout")
    me_after = second.get("/api/auth/me").json()
    assert me_after["authenticated"] is False
    assert me_after["workspace_id"] == ws_guest
    # Guest work survived; owned work is no longer visible anonymously.
    assert second.get(f"/api/jobs/{guest_job['id']}").status_code == 200
    assert jobs.get(guest_job["id"], ws_guest) is not None


def test_claim_never_steals_foreign_owned_workspace(monkeypatch):
    from prior import auth as auth_mod
    from prior import settings as settings_mod

    a = make_client()
    ws_a = guest_ws(a)
    google_login(a, monkeypatch, sub="google-sub-a", email="a@example.com")
    store = IdentityStore(settings_mod.identity_db_path())
    acct_a = store.find_account_by_identity("google", "google-sub-a")
    assert acct_a and store.owned_workspace(str(acct_a["id"])) == ws_a

    # A second account presenting A's owned workspace cookie must NOT steal it.
    acct_b, _ = auth_mod.find_or_create_account(store, "google", "google-sub-b", "b@example.com", "B")
    effective, claimed, preserved = auth_mod.claim_or_resolve(store, str(acct_b["id"]), ws_a)
    assert effective != ws_a
    assert store.workspace_owner(ws_a) == str(acct_a["id"])
    assert preserved is None  # foreign owned cookie is not surfaced as mergeable


# ---- security gate: strict OIDC validation ----

def test_google_wrong_nonce_fails(monkeypatch):
    client = make_client()
    guest_ws(client)
    done, _ = google_callback(client, monkeypatch, nonce_mode="wrong-nonce-value")
    assert done.status_code == 302
    assert "reason=provider" in done.headers["location"]
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_google_missing_nonce_fails(monkeypatch):
    client = make_client()
    guest_ws(client)
    done, _ = google_callback(client, monkeypatch, nonce_mode="omit")
    assert done.status_code == 302
    assert "reason=provider" in done.headers["location"]
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_google_invalid_issuer_fails(monkeypatch):
    client = make_client()
    guest_ws(client)
    done, _ = google_callback(client, monkeypatch, iss="https://evil.example.com")
    assert "reason=provider" in done.headers["location"]
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_google_invalid_audience_fails(monkeypatch):
    client = make_client()
    guest_ws(client)
    done, _ = google_callback(client, monkeypatch, aud="some-other-client-id")
    assert "reason=provider" in done.headers["location"]
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_google_expired_token_fails(monkeypatch):
    client = make_client()
    guest_ws(client)
    done, _ = google_callback(client, monkeypatch, exp_offset=-3600)
    assert "reason=" in done.headers["location"]
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_google_missing_subject_fails(monkeypatch):
    client = make_client()
    guest_ws(client)
    done, _ = google_callback(client, monkeypatch, include_sub=False)
    assert "reason=provider" in done.headers["location"]
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_verify_google_id_token_uses_official_library(monkeypatch):
    """Production verifier delegates signature/issuer/audience/expiry to
    google-auth (not tokeninfo, not hand-rolled crypto)."""
    import prior.auth as auth_mod

    monkeypatch.setenv("GOOGLE_CLIENT_ID", GOOGLE_ID)
    calls = {}

    class FakeRequest:
        pass

    def fake_verify(token, request, audience=None, clock_skew_in_seconds=0):
        calls["token"] = token
        calls["audience"] = audience
        assert isinstance(request, FakeRequest)
        return {"sub": "s", "aud": audience, "iss": "https://accounts.google.com",
                "exp": 9999999999, "nonce": "n"}

    monkeypatch.setattr("google.auth.transport.requests.Request", FakeRequest)
    monkeypatch.setattr("google.oauth2.id_token.verify_oauth2_token", fake_verify)
    out = auth_mod.verify_google_id_token("raw-token")
    assert out["sub"] == "s"
    assert calls == {"token": "raw-token", "audience": GOOGLE_ID}

    def fake_verify_bad(token, request, audience=None, clock_skew_in_seconds=0):
        raise ValueError("bad signature")

    monkeypatch.setattr("google.oauth2.id_token.verify_oauth2_token", fake_verify_bad)
    with pytest.raises(auth_mod.AuthError):
        auth_mod.verify_google_id_token("bad-token")


# ---- security gate: email OTP invariants ----

def test_email_claim_obeys_owned_workspace_invariant(monkeypatch):
    client = make_client()
    ws = guest_ws(client)
    job_id, _ = seed_history(client, ws)
    email_login(client, monkeypatch, email="user@example.com")
    client.post("/api/auth/logout")
    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is False
    assert me["workspace_id"] != ws
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    mem = client.get("/api/memory").json()
    assert mem["count"] == 0


def test_email_token_single_use(monkeypatch):
    from prior import auth as auth_mod

    client = make_client()
    guest_ws(client)
    mock_email_code(monkeypatch, "123456")
    assert client.post("/api/auth/email/start", json={"email": "once@example.com"}).status_code == 200
    first = client.post("/api/auth/email/verify", json={"email": "once@example.com", "code": "123456"})
    assert first.status_code == 200
    client.post("/api/auth/logout")
    # Replaying the same code must fail (token already consumed).
    with pytest.raises(auth_mod.AuthError):
        auth_mod.verify_email_code("once@example.com", "123456")


def test_email_token_expiry(monkeypatch):
    from prior import auth as auth_mod
    from prior import settings as settings_mod

    store = IdentityStore(settings_mod.identity_db_path())
    token_hash = hash_token("aged@example.com:654321")
    store.create_email_token(token_hash, "aged@example.com", "ws_deadbeefdeadbeef", -1)
    with pytest.raises(auth_mod.AuthError):
        auth_mod.verify_email_code("aged@example.com", "654321")


def test_rate_limiting_enforced(monkeypatch):
    from prior import settings as settings_mod

    store = IdentityStore(settings_mod.identity_db_path())
    key = "test-rate-limit-key"
    for _ in range(3):
        assert store.check_rate(key, limit=3, window_s=60) is True
    assert store.check_rate(key, limit=3, window_s=60) is False

    # Email send path is rate-limited per address (5/hour).
    client = make_client()
    guest_ws(client)
    mock_email_code(monkeypatch, "123456")
    for _ in range(5):
        resp = client.post("/api/auth/email/start", json={"email": "flood@example.com"})
        assert resp.status_code == 200
    limited = client.post("/api/auth/email/start", json={"email": "flood@example.com"})
    assert limited.status_code == 429


# ---- final gate: logout revokes EVERY presented same-name session ----

def _presented_logout(client: TestClient, raw_cookie: str) -> dict:
    resp = client.post("/api/auth/logout", headers={"cookie": raw_cookie})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_logout_revokes_all_presented_same_name_sessions(monkeypatch):
    from prior import settings as settings_mod

    client = make_client()
    ws = guest_ws(client)
    seed_history(client, ws)
    google_login(client, monkeypatch)
    account_id = client.get("/api/auth/me").json()["account"]["account_id"]
    store = IdentityStore(settings_mod.identity_db_path())
    s1 = client.cookies.get("prior_session")
    assert s1 and store.lookup_session(s1) is not None
    s2 = store.create_session(account_id, ttl_s=3600)
    assert store.lookup_session(s2) is not None
    assert _presented_logout(
        client, f"prior_session={s1}; prior_session={s2}; prior_workspace={ws}"
    ) == {"ok": True}
    assert store.lookup_session(s1) is None
    assert store.lookup_session(s2) is None


def test_logout_revokes_mixed_valid_and_invalid_candidates(monkeypatch):
    from prior import settings as settings_mod

    client = make_client()
    ws = guest_ws(client)
    seed_history(client, ws)
    google_login(client, monkeypatch)
    account_id = client.get("/api/auth/me").json()["account"]["account_id"]
    store = IdentityStore(settings_mod.identity_db_path())
    s1 = client.cookies.get("prior_session")
    s2 = store.create_session(account_id, ttl_s=3600)
    assert _presented_logout(
        client,
        f"prior_session=bogus-token; prior_session={s1}; prior_session={s2}"
        f"; prior_workspace={ws}",
    ) == {"ok": True}
    assert store.lookup_session(s1) is None
    assert store.lookup_session(s2) is None


def test_former_presented_sessions_cannot_authenticate_afterward(monkeypatch):
    from prior import settings as settings_mod

    client = make_client()
    ws = guest_ws(client)
    job_id, _ = seed_history(client, ws)
    google_login(client, monkeypatch)
    account_id = client.get("/api/auth/me").json()["account"]["account_id"]
    store = IdentityStore(settings_mod.identity_db_path())
    s1 = client.cookies.get("prior_session")
    s2 = store.create_session(account_id, ttl_s=3600)
    _presented_logout(client, f"prior_session={s1}; prior_session={s2}; prior_workspace={ws}")
    for stale in (s1, s2):
        probe = make_client()
        probe.cookies.set("prior_session", stale)
        probe.cookies.set("prior_workspace", ws)
        me = probe.get("/api/auth/me").json()
        assert me["authenticated"] is False
        assert me["workspace_id"] != ws
        assert probe.get(f"/api/jobs/{job_id}").status_code == 404


def test_logout_preserves_unpresented_cross_device_session(monkeypatch):
    from prior import settings as settings_mod

    client = make_client()
    ws = guest_ws(client)
    seed_history(client, ws)
    google_login(client, monkeypatch)
    account_id = client.get("/api/auth/me").json()["account"]["account_id"]
    store = IdentityStore(settings_mod.identity_db_path())
    s1 = client.cookies.get("prior_session")
    s2 = store.create_session(account_id, ttl_s=3600)
    device_b = store.create_session(account_id, ttl_s=3600)
    _presented_logout(client, f"prior_session={s1}; prior_session={s2}; prior_workspace={ws}")
    assert store.lookup_session(s1) is None
    assert store.lookup_session(s2) is None
    # Same account, other device, never presented here: still valid.
    assert store.lookup_session(device_b) is not None
    other = make_client()
    other.cookies.set("prior_session", device_b)
    me = other.get("/api/auth/me").json()
    assert me["authenticated"] is True
    assert me["workspace_id"] == ws
