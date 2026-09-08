"""Post-logout auth-status UI regressions (owner UAT bug).

Frontend truth must come from /api/auth/me, never from a stale
?auth=signed-in query string. The node harness executes the REAL
src/prior/static/app.js bundle; the integrated test ties the banner/URL
invariant to real backend session truth using isolated test stores.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from test_auth import google_login, guest_ws, make_client, seed_history

HARNESS = Path(__file__).with_name("auth_status_check.cjs")
APP_JS = Path(__file__).parents[1] / "src" / "prior" / "static" / "app.js"


def _run_node_harness(result_file: Path) -> subprocess.CompletedProcess:
    # NOTE: stdio is inherited, not piped: this sandbox's pytest process
    # fails Windows handle duplication for piped children (WinError 6/50).
    # The harness reports via exit code + result file instead.
    last: OSError | None = None
    for _ in range(3):
        try:
            return subprocess.run(
                ["node", str(HARNESS), str(result_file)], timeout=60
            )
        except OSError as exc:  # transient spawn race; retry
            last = exc
    raise last  # type: ignore[misc]


def test_signed_in_banner_logic_via_real_bundle(tmp_path):
    if shutil.which("node") is None:
        import pytest

        pytest.skip("node unavailable")
    result_file = tmp_path / "frontend_auth_status.txt"
    proc = _run_node_harness(result_file)
    assert proc.returncode == 0
    assert result_file.read_text(encoding="utf-8").strip() == "FRONTEND_AUTH_STATUS_OK"


def test_bundle_has_no_unconsumed_signed_in_source():
    src = APP_JS.read_text(encoding="utf-8")
    # The success copy may only be emitted through the consumed-notice path.
    assert "Signed in. Your PRIOR memory follows you" in src
    assert "consumeAuthQueryParam" in src
    # Backend emits the one-time signal exactly once (Google callback).
    assert src.count("auth=signed-in") == 0  # frontend never fabricates it


def test_post_logout_state_and_recovery_with_stale_query(monkeypatch):
    """Backend truth across the owner UAT sequence with a stale query string.

    login (?auth=signed-in issued) -> logout -> guest restored, owned W
    denied anonymously even when the stale query is presented -> re-login
    restores the owned workspace.
    """
    client = make_client()
    ws_guest = guest_ws(client)
    me = google_login(client, monkeypatch)
    ws_owned = me["workspace_id"]
    assert ws_owned == ws_guest  # first claim keeps the same ID
    job_id, _ = seed_history(client, ws_owned)

    assert client.post("/api/auth/logout").json() == {"ok": True}

    # Post-logout authoritative state: unauthenticated, safe guest, owned denied.
    after = client.get("/api/auth/me").json()
    assert after["authenticated"] is False
    assert after["account"] is None
    assert after["workspace_id"] != ws_owned
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    assert client.get("/api/memory").json()["count"] == 0

    # A stale ?auth=signed-in query string changes nothing server-side.
    stale = client.get("/api/auth/me?auth=signed-in").json()
    assert stale["authenticated"] is False
    assert client.get(f"/api/jobs/{job_id}?auth=signed-in").status_code == 404

    # Re-login restores the original owned workspace with history intact.
    again = google_login(client, monkeypatch)
    assert again["workspace_id"] == ws_owned
    assert client.get(f"/api/jobs/{job_id}").status_code == 200
    assert client.get("/api/memory").json()["count"] == 1


def test_login_still_issues_signed_in_signal(monkeypatch):
    from urllib.parse import parse_qs, urlparse

    from prior import auth as auth_mod

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "sig-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "sig-secret")
    captured: dict = {}

    def fake_exchange(code, uri, verifier):
        captured["verifier"] = verifier
        return {"id_token": "stub"}

    import time

    def fake_verify(token):
        return {
            "iss": "https://accounts.google.com",
            "aud": "sig-client",
            "sub": "sig-sub",
            "exp": int(time.time()) + 3600,
            "nonce": captured["nonce"],
            "email_verified": "false",
        }

    monkeypatch.setattr(auth_mod, "google_token_exchange", fake_exchange)
    monkeypatch.setattr(auth_mod, "verify_google_id_token", fake_verify)
    client = make_client()
    guest_ws(client)
    start = client.get("/api/auth/google/start", follow_redirects=False)
    assert start.status_code in (302, 307)
    qs = parse_qs(urlparse(start.headers["location"]).query)
    captured["nonce"] = qs["nonce"][0]
    done = client.get(
        f"/api/auth/google/callback?code=x&state={qs['state'][0]}",
        follow_redirects=False,
    )
    assert done.status_code == 302
    assert "auth=signed-in" in done.headers["location"]
    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is True
    assert me["workspace_id"]
