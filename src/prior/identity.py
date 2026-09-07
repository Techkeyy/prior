"""Durable user identity store (stdlib sqlite3, no new dependencies).

Layers, top to bottom:

    Account  --owns-->  Workspace  --contains-->  Jobs / Lessons / Sibyl memory

The workspace abstraction is unchanged: jobs keep binding to workspace_id
strings in jobs.json and Sibyl keeps tenant_id = workspace_id. This store
only records OWNERSHIP (which account owns which workspace) plus the auth
machinery (identities, sessions, OAuth state, email tokens, rate counters).

Merge policy (hard rule, no silent merges):
- First login from a guest browser CLAIMS that browser's workspace:
  same workspace ID, same jobs, same lessons, zero data movement.
- A returning account that already owns a workspace always resolves to
  that owned workspace. An unrelated guest workspace in the same browser
  is preserved untouched and surfaced for a future explicit decision;
  it is never merged automatically.
- Identity key is always (provider, provider_subject). Email alone never
  merges accounts across providers. Different provider subjects are
  different accounts, even with equal display names or emails.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
import time
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL,
    primary_email TEXT,
    display_name TEXT
);
CREATE TABLE IF NOT EXISTS auth_identities (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    provider TEXT NOT NULL,
    provider_subject TEXT NOT NULL,
    normalized_email TEXT,
    created_at INTEGER NOT NULL,
    last_login_at INTEGER NOT NULL,
    UNIQUE(provider, provider_subject)
);
CREATE INDEX IF NOT EXISTS idx_identities_account ON auth_identities(account_id);
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    account_id TEXT REFERENCES accounts(id),
    created_at INTEGER NOT NULL,
    claimed_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_workspaces_account ON workspaces(account_id);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    revoked_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sessions_account ON sessions(account_id);
CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY,
    nonce TEXT NOT NULL,
    verifier TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    used_at INTEGER
);
CREATE TABLE IF NOT EXISTS email_tokens (
    token_hash TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    used_at INTEGER,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS rate_counters (
    scope_key TEXT PRIMARY KEY,
    window_start INTEGER NOT NULL,
    count INTEGER NOT NULL
);
"""

_lock = threading.Lock()


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(_SCHEMA)
    return conn


def now_s() -> int:
    return int(time.time())


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def valid_email(email: str) -> bool:
    norm = normalize_email(email)
    if not norm or len(norm) > 254 or "@" not in norm:
        return False
    local, _, domain = norm.partition("@")
    return bool(local) and "." in domain and " " not in norm


class IdentityStore:
    """Thin SQLite registry. One instance per process is enough; methods
    open short-lived connections guarded by a lock (same convention as
    prior.jobs)."""

    def __init__(self, db_path: str) -> None:
        self.db_path = str(db_path)

    def _db(self) -> sqlite3.Connection:
        return _connect(self.db_path)

    # ---- accounts / identities ----

    def find_account_by_identity(self, provider: str, subject: str) -> dict[str, Any] | None:
        with _lock, self._db() as db:
            row = db.execute(
                "SELECT a.* FROM accounts a JOIN auth_identities i ON i.account_id = a.id"
                " WHERE i.provider = ? AND i.provider_subject = ?",
                (provider, subject),
            ).fetchone()
            return dict(row) if row else None

    def create_account(
        self, provider: str, subject: str, email: str | None, display_name: str | None
    ) -> dict[str, Any]:
        account_id = new_id("acct")
        now = now_s()
        with _lock, self._db() as db:
            db.execute(
                "INSERT INTO accounts (id, created_at, primary_email, display_name)"
                " VALUES (?, ?, ?, ?)",
                (account_id, now, email, display_name),
            )
            db.execute(
                "INSERT INTO auth_identities (id, account_id, provider, provider_subject,"
                " normalized_email, created_at, last_login_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (new_id("idn"), account_id, provider, subject, email, now, now),
            )
            row = db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
            return dict(row)

    def touch_login(self, account_id: str, provider: str, subject: str) -> None:
        with _lock, self._db() as db:
            db.execute(
                "UPDATE auth_identities SET last_login_at = ?"
                " WHERE account_id = ? AND provider = ? AND provider_subject = ?",
                (now_s(), account_id, provider, subject),
            )

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        with _lock, self._db() as db:
            row = db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
            return dict(row) if row else None

    def count_identities(self, account_id: str, provider: str, subject: str) -> int:
        with _lock, self._db() as db:
            row = db.execute(
                "SELECT COUNT(*) AS n FROM auth_identities"
                " WHERE account_id = ? AND provider = ? AND provider_subject = ?",
                (account_id, provider, subject),
            ).fetchone()
            return int(row["n"])

    def count_accounts(self) -> int:
        with _lock, self._db() as db:
            row = db.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()
            return int(row["n"])

    # ---- workspaces (ownership registry only) ----

    def ensure_workspace_row(self, workspace_id: str) -> None:
        with _lock, self._db() as db:
            db.execute(
                "INSERT OR IGNORE INTO workspaces (id, account_id, created_at, claimed_at)"
                " VALUES (?, NULL, ?, NULL)",
                (workspace_id, now_s()),
            )

    def owned_workspace(self, account_id: str) -> str | None:
        with _lock, self._db() as db:
            row = db.execute(
                "SELECT id FROM workspaces WHERE account_id = ? ORDER BY claimed_at ASC LIMIT 1",
                (account_id,),
            ).fetchone()
            return str(row["id"]) if row else None

    def claim_workspace(self, workspace_id: str, account_id: str) -> None:
        """Claim a guest workspace for an account. Same ID, zero data
        movement. Precondition (enforced by caller): the account owns no
        workspace yet."""
        now = now_s()
        with _lock, self._db() as db:
            db.execute(
                "INSERT INTO workspaces (id, account_id, created_at, claimed_at)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET account_id = excluded.account_id,"
                " claimed_at = excluded.claimed_at",
                (workspace_id, account_id, now, now),
            )

    def workspace_owner(self, workspace_id: str) -> str | None:
        with _lock, self._db() as db:
            row = db.execute(
                "SELECT account_id FROM workspaces WHERE id = ?", (workspace_id,)
            ).fetchone()
            return str(row["account_id"]) if row and row["account_id"] else None

    # ---- sessions (PRIOR's own; never provider tokens) ----

    def create_session(self, account_id: str, ttl_s: int) -> str:
        token = secrets.token_urlsafe(32)
        now = now_s()
        with _lock, self._db() as db:
            db.execute(
                "INSERT INTO sessions (token_hash, account_id, created_at, expires_at, revoked_at)"
                " VALUES (?, ?, ?, ?, NULL)",
                (hash_token(token), account_id, now, now + ttl_s),
            )
        return token

    def lookup_session(self, token: str) -> dict[str, Any] | None:
        with _lock, self._db() as db:
            row = db.execute(
                "SELECT * FROM sessions WHERE token_hash = ?", (hash_token(token),)
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            if data["revoked_at"] is not None or data["expires_at"] <= now_s():
                return None
            return data

    def refresh_session(self, token: str, ttl_s: int) -> None:
        with _lock, self._db() as db:
            db.execute(
                "UPDATE sessions SET expires_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                (now_s() + ttl_s, hash_token(token)),
            )

    def revoke_session(self, token: str) -> None:
        with _lock, self._db() as db:
            db.execute(
                "UPDATE sessions SET revoked_at = ? WHERE token_hash = ?",
                (now_s(), hash_token(token)),
            )

    def revoke_account_sessions(self, account_id: str) -> int:
        with _lock, self._db() as db:
            cur = db.execute(
                "UPDATE sessions SET revoked_at = ? WHERE account_id = ? AND revoked_at IS NULL",
                (now_s(), account_id),
            )
            return cur.rowcount

    # ---- OAuth state / PKCE / nonce (single-use, short-lived) ----

    def create_oauth_state(
        self, state: str, nonce: str, verifier: str, workspace_id: str,
        provider: str, ttl_s: int,
    ) -> None:
        now = now_s()
        with _lock, self._db() as db:
            db.execute(
                "INSERT INTO oauth_states (state, nonce, verifier, workspace_id, provider,"
                " created_at, expires_at, used_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (state, nonce, verifier, workspace_id, provider, now, now + ttl_s),
            )

    def consume_oauth_state(self, state: str) -> dict[str, Any] | None:
        """Fetch-and-mark-used atomically enough for this single-worker app.
        Returns the row, or None when missing/expired/already used."""
        with _lock, self._db() as db:
            row = db.execute(
                "SELECT * FROM oauth_states WHERE state = ?", (state,)
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            if data["used_at"] is not None or data["expires_at"] <= now_s():
                return None
            db.execute(
                "UPDATE oauth_states SET used_at = ? WHERE state = ?", (now_s(), state)
            )
            return data

    # ---- email tokens (single-use, short-lived, attempt-counted) ----

    def create_email_token(
        self, token_hash: str, email: str, workspace_id: str, ttl_s: int
    ) -> None:
        now = now_s()
        with _lock, self._db() as db:
            db.execute(
                "INSERT INTO email_tokens (token_hash, email, workspace_id, created_at,"
                " expires_at, used_at, attempts)"
                " VALUES (?, ?, ?, ?, ?, NULL, 0)",
                (token_hash, email, workspace_id, now, now + ttl_s),
            )

    def get_email_token(self, token_hash: str) -> dict[str, Any] | None:
        with _lock, self._db() as db:
            row = db.execute(
                "SELECT * FROM email_tokens WHERE token_hash = ?", (token_hash,)
            ).fetchone()
            return dict(row) if row else None

    def bump_email_attempts(self, token_hash: str) -> int:
        with _lock, self._db() as db:
            db.execute(
                "UPDATE email_tokens SET attempts = attempts + 1 WHERE token_hash = ?",
                (token_hash,),
            )
            row = db.execute(
                "SELECT attempts FROM email_tokens WHERE token_hash = ?", (token_hash,)
            ).fetchone()
            return int(row["attempts"]) if row else 0

    def consume_email_token(self, token_hash: str) -> dict[str, Any] | None:
        with _lock, self._db() as db:
            row = db.execute(
                "SELECT * FROM email_tokens WHERE token_hash = ?", (token_hash,)
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            if data["used_at"] is not None or data["expires_at"] <= now_s():
                return None
            db.execute(
                "UPDATE email_tokens SET used_at = ? WHERE token_hash = ?",
                (now_s(), token_hash),
            )
            return data

    def invalidate_email_tokens(self, email: str) -> None:
        with _lock, self._db() as db:
            db.execute("DELETE FROM email_tokens WHERE email = ?", (email,))

    # ---- generic rate counters (sliding fixed windows) ----

    def check_rate(self, scope_key: str, limit: int, window_s: int) -> bool:
        """True when the action is allowed (and counted). False when over limit."""
        now = now_s()
        with _lock, self._db() as db:
            row = db.execute(
                "SELECT window_start, count FROM rate_counters WHERE scope_key = ?",
                (scope_key,),
            ).fetchone()
            if not row or int(row["window_start"]) + window_s <= now:
                db.execute(
                    "INSERT INTO rate_counters (scope_key, window_start, count)"
                    " VALUES (?, ?, 1)"
                    " ON CONFLICT(scope_key) DO UPDATE SET window_start = excluded.window_start,"
                    " count = excluded.count",
                    (scope_key, now),
                )
                return True
            if int(row["count"]) >= limit:
                return False
            db.execute(
                "UPDATE rate_counters SET count = count + 1 WHERE scope_key = ?",
                (scope_key,),
            )
            return True
