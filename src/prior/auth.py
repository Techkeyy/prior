"""Durable user identity: Google OIDC, email OTP, PRIOR sessions, workspace claiming.

Research engine is untouched. This module only answers: *which account (if
any) is behind this request, and therefore which workspace is effective?*

Rules enforced here:
- Identity key is (provider, provider_subject). Email never merges accounts.
- First login CLAIMS the current guest workspace: same ID, zero data movement.
- A returning account resolves to its owned workspace. Unrelated guest
  workspaces are never merged; they are preserved and surfaced.
- PRIOR sessions are random bearer tokens (sha256-stored). Provider OAuth
  tokens are used once at login and never stored.
- Google ID tokens are verified server-side with Google's official
  `google-auth` library (`verify_oauth2_token`: signature via Google certs,
  issuer, audience, expiry) plus an explicit strict nonce comparison.
  No custom cryptography. The `tokeninfo` endpoint is NOT used in
  production (Google documents it as debugging-only).
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import smtplib
import time
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlencode

import httpx

from prior import settings
from prior.identity import IdentityStore, hash_token, normalize_email, valid_email

SESSION_COOKIE = "prior_session"
WORKSPACE_COOKIE = "prior_workspace"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
OAUTH_STATE_TTL_S = 600
EMAIL_CODE_TTL_S = 600
EMAIL_MAX_ATTEMPTS = 10


class AuthError(RuntimeError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def get_store() -> IdentityStore:
    return IdentityStore(settings.identity_db_path())


def session_cookie_kwargs() -> dict[str, Any]:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": settings.cookie_secure(),
        "path": "/",
        "max_age": settings.session_ttl_seconds(),
    }


def workspace_cookie_kwargs() -> dict[str, Any]:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": settings.cookie_secure(),
        "max_age": 60 * 60 * 24 * 400,
    }


def account_view(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_id": account.get("id"),
        "email": account.get("primary_email"),
        "display_name": account.get("display_name"),
    }


# ---- workspace resolution / claiming ----

def _session_candidates(request) -> list[str]:
    """All session cookie values on the request. Browsers can rarely present
    two same-name cookies (stale domain variants); each is tried until one
    validates instead of trusting the first."""
    seen: list[str] = []
    raw = request.headers.get("cookie", "") if hasattr(request, "headers") else ""
    for part in raw.split(";"):
        name, sep, value = part.partition("=")
        if sep and name.strip() == SESSION_COOKIE:
            token = value.strip()
            if token and token not in seen:
                seen.append(token)
    single = request.cookies.get(SESSION_COOKIE)
    if single and single not in seen:
        seen.append(single)
    return seen


def mint_guest_workspace(store: IdentityStore, response) -> str:
    guest_ws = "ws_" + secrets.token_hex(8)
    store.ensure_workspace_row(guest_ws)
    response.set_cookie(
        WORKSPACE_COOKIE, guest_ws, **workspace_cookie_kwargs()
    )
    return guest_ws


def reject_owned_guest_cookie(store: IdentityStore, workspace_id: str, response) -> str:
    """Central invariant: an unauthenticated guest cookie MUST NOT resolve
    a workspace that already has an owner. Rotate to a fresh unowned guest."""
    if workspace_id and store.workspace_owner(workspace_id) is None:
        store.ensure_workspace_row(workspace_id)
        return workspace_id
    return mint_guest_workspace(store, response)


def resolve_effective_workspace(
    request, response, issue_guest_fn
) -> tuple[str, dict[str, Any] | None]:
    """Return (workspace_id, account|None). Authenticated sessions resolve to
    the owned workspace. The anonymous cookie path never opens an owned
    workspace: ownership is checked here, not only at logout."""
    store = get_store()
    for token in _session_candidates(request):
        data = store.lookup_session(token)
        if not data:
            continue
        account = store.get_account(str(data["account_id"]))
        if not account:
            continue
        owned = store.owned_workspace(str(account["id"]))
        store.refresh_session(token, settings.session_ttl_seconds())
        if owned:
            return owned, account
    guest_ws = issue_guest_fn(request, response)
    return reject_owned_guest_cookie(store, guest_ws, response), None


def claim_or_resolve(
    store: IdentityStore, account_id: str, guest_ws: str
) -> tuple[str, bool, str | None]:
    """Returns (effective_workspace, claimed_now, preserved_guest_or_None).

    Never steals a workspace already owned by another account. Unowned guest
    workspaces are claimed on first login or preserved (not merged) when the
    account already owns a workspace."""
    if guest_ws:
        store.ensure_workspace_row(guest_ws)
    owned = store.owned_workspace(account_id)
    guest_owner = store.workspace_owner(guest_ws) if guest_ws else None
    guest_is_free = bool(guest_ws) and guest_owner is None
    if owned is None:
        if guest_is_free:
            store.claim_workspace(guest_ws, account_id)
            return guest_ws, True, None
        fresh = "ws_" + secrets.token_hex(8)
        store.claim_workspace(fresh, account_id)
        return fresh, True, None
    if owned == guest_ws:
        return guest_ws, False, None
    preserved = guest_ws if guest_is_free else None
    return owned, False, preserved


def find_or_create_account(
    store: IdentityStore, provider: str, subject: str,
    email: str | None, display_name: str | None,
) -> tuple[dict[str, Any], bool]:
    existing = store.find_account_by_identity(provider, subject)
    if existing:
        store.touch_login(str(existing["id"]), provider, subject)
        return store.get_account(str(existing["id"])) or existing, False
    account = store.create_account(provider, subject, email, display_name)
    return account, True


# ---- Google OIDC ----

def google_callback_url() -> str:
    return settings.public_url().rstrip("/") + "/api/auth/google/callback"


def google_config_error() -> dict[str, Any]:
    return {
        "error": "google_not_configured",
        "message": (
            "Google sign-in is not configured on this server yet. "
            "Guest mode keeps working normally."
        ),
    }


def start_google_login(guest_ws: str, client_ip: str = "unknown") -> str:
    if not settings.google_configured():
        raise AuthError(google_config_error()["message"], status=503)
    store = get_store()
    if not store.check_rate("oauth-start-ip:" + client_ip[:64], limit=30, window_s=60):
        raise AuthError("Too many login attempts. Try again shortly.", status=429)
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    store.create_oauth_state(
        state, nonce, verifier, guest_ws, "google", OAUTH_STATE_TTL_S
    )
    params = {
        "client_id": settings.google_client_id(),
        "redirect_uri": google_callback_url(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def google_token_exchange(code: str, redirect_uri: str, verifier: str) -> dict[str, Any]:
    try:
        resp = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id(),
                "client_secret": settings.google_client_secret(),
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
            timeout=15.0,
        )
    except Exception as exc:
        raise AuthError("Login provider is unreachable. Try again.", status=502) from exc
    if resp.status_code != 200:
        raise AuthError("Login failed at the provider. Try again.", status=502)
    try:
        return dict(resp.json())
    except Exception as exc:
        raise AuthError("Login failed at the provider. Try again.", status=502) from exc


def verify_google_id_token(id_token_str: str) -> dict[str, Any]:
    """Verify a Google ID token with Google's official auth library.

    Per https://developers.google.com/identity/sign-in/web/backend-auth and
    https://developers.google.com/identity/gsi/web/guides/verify-google-id-token:
    production verification must check the JWT signature against Google's
    public keys plus aud/iss/exp — via a Google API client library — and the
    `tokeninfo` endpoint is debugging-only (throttled, unsuitable for
    production). `verify_oauth2_token` performs signature + issuer + audience
    + expiry verification. Nonce is bound explicitly by the caller in
    `finish_google_login` (strict: missing or mismatched nonce fails).
    """
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
    except Exception as exc:
        raise AuthError("Login verification failed. Try again.", status=502) from exc
    try:
        request = google_requests.Request()
        info = google_id_token.verify_oauth2_token(
            id_token_str,
            request,
            audience=settings.google_client_id(),
            clock_skew_in_seconds=30,
        )
    except Exception as exc:
        raise AuthError("Login verification failed. Try again.", status=502) from exc
    try:
        return dict(info)
    except Exception as exc:
        raise AuthError("Login verification failed. Try again.", status=502) from exc


def google_tokeninfo(id_token: str) -> dict[str, Any]:
    """Deprecated alias. Production path is `verify_google_id_token`."""
    return verify_google_id_token(id_token)


def finish_google_login(code: str, state: str) -> dict[str, Any]:
    store = get_store()
    saved = store.consume_oauth_state(state)
    if not saved:
        raise AuthError("Login session expired or already used. Start again.", status=400)
    tokens = google_token_exchange(code, google_callback_url(), str(saved["verifier"]))
    id_token = str(tokens.get("id_token") or "")
    if not id_token:
        raise AuthError("Login failed at the provider. Try again.", status=502)
    info = verify_google_id_token(id_token)
    if str(info.get("iss") or "") not in GOOGLE_ISSUERS:
        raise AuthError("Login verification failed. Try again.", status=502)
    if str(info.get("aud") or "") != settings.google_client_id():
        raise AuthError("Login verification failed. Try again.", status=502)
    try:
        exp = int(info.get("exp") or 0)
    except (TypeError, ValueError):
        raise AuthError("Login verification failed. Try again.", status=502) from None
    if exp <= int(time.time()) + 30:
        raise AuthError("Login session expired. Start again.", status=400)
    echoed_nonce = str(info.get("nonce") or "")
    expected_nonce = str(saved["nonce"] or "")
    if not echoed_nonce or not expected_nonce or echoed_nonce != expected_nonce:
        raise AuthError("Login verification failed. Try again.", status=502)
    subject = str(info.get("sub") or "")
    if not subject:
        raise AuthError("Login verification failed. Try again.", status=502)
    email: str | None = None
    if str(info.get("email_verified") or "").lower() == "true":
        candidate = normalize_email(str(info.get("email") or ""))
        email = candidate if valid_email(candidate) else None
    display_name = str(info.get("name") or "").strip()[:120] or None
    account, created = find_or_create_account(
        store, "google", subject, email, display_name
    )
    return {
        "account": account,
        "created": created,
        "guest_workspace": str(saved["workspace_id"]),
        "provider": "google",
    }


# ---- email OTP (magic code) ----

def _new_email_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def send_email_otp(recipient: str, code: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Your PRIOR sign-in code"
    message["From"] = settings.email_from()
    message["To"] = recipient
    message.set_content(
        f"Your PRIOR sign-in code is: {code}\n\n"
        f"It expires in {EMAIL_CODE_TTL_S // 60} minutes. "
        "If you did not request it, ignore this email.\n"
    )
    port = settings.email_smtp_port()
    tls_mode = settings.email_smtp_tls()
    if tls_mode == "ssl" or port == 465:
        session = smtplib.SMTP_SSL(settings.email_smtp_host(), port, timeout=20)
    else:
        session = smtplib.SMTP(settings.email_smtp_host(), port, timeout=20)
        if tls_mode == "starttls":
            session.starttls()
    try:
        user = settings.email_smtp_user()
        if user:
            session.login(user, settings.email_smtp_password())
        session.send_message(message)
    finally:
        try:
            session.quit()
        except Exception:
            pass


def start_email_login(email: str, guest_ws: str, client_ip: str) -> dict[str, Any]:
    """Always returns the same shape (no account enumeration)."""
    store = get_store()
    norm = normalize_email(email)
    if valid_email(norm):
        if not store.check_rate(f"email-send:{norm}", limit=5, window_s=3600):
            raise AuthError("Too many codes requested. Try again later.", status=429)
        if not store.check_rate(f"email-send-ip:{client_ip}", limit=20, window_s=3600):
            raise AuthError("Too many codes requested. Try again later.", status=429)
        store.invalidate_email_tokens(norm)
        code = _new_email_code()
        store.create_email_token(hash_token(norm + ":" + code), norm, guest_ws, EMAIL_CODE_TTL_S)
        if settings.email_configured():
            try:
                send_email_otp(norm, code)
            except Exception as exc:
                raise AuthError("Email delivery failed. Try again later.", status=502) from exc
            return {"ok": True, "delivery": "sent"}
    return {"ok": True, "delivery": "not_configured"}


def verify_email_code(email: str, code: str) -> dict[str, Any]:
    store = get_store()
    norm = normalize_email(email)
    candidate = (code or "").strip()
    if not valid_email(norm) or not candidate:
        raise AuthError("Invalid code. Try again.", status=400)
    row = store.get_email_token(hash_token(norm + ":" + candidate))
    if not row:
        raise AuthError("Invalid code. Try again.", status=400)
    if int(row["attempts"]) >= EMAIL_MAX_ATTEMPTS:
        store.invalidate_email_tokens(norm)
        raise AuthError("Too many attempts. Request a new code.", status=429)
    if row["used_at"] is not None or int(row["expires_at"]) <= int(time.time()):
        raise AuthError("Code expired or already used. Request a new one.", status=400)
    store.bump_email_attempts(str(row["token_hash"]))
    claimed = store.consume_email_token(str(row["token_hash"]))
    if not claimed:
        raise AuthError("Code expired or already used. Request a new one.", status=400)
    account, created = find_or_create_account(store, "email", norm, norm, None)
    return {
        "account": account,
        "created": created,
        "guest_workspace": str(claimed["workspace_id"]),
        "provider": "email",
    }
