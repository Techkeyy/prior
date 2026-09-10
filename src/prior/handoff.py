"""Temporary one-click workspace handoff for owner UAT.

A handoff token is a high-entropy, opaque, single-use, short-lived server
capability that binds exactly one pre-chosen guest workspace to the
``prior_workspace`` cookie. It is NOT general workspace switching:

- the token is random and carries no information: the workspace id never
  appears in (or is derivable from) the public URL;
- the server keeps the only token -> workspace mapping, so a URL edit can
  only produce an unknown token, never a different workspace;
- every token expires (10 minutes by default) and is deleted atomically on
  its first successful redemption, so it cannot be replayed or shared;
- redemption performs no ACP write and mutates no job, lesson, or ownership
  record — it only sets the same cookie a guest already receives.
"""

from __future__ import annotations

import hmac as _hmac
import json
import re
import secrets
import threading
import time
from typing import Any

from prior import settings

TOKEN_TTL_SECONDS = 10 * 60
WORKSPACE_PATTERN = re.compile(r"^ws_[a-f0-9]{16}$")
_LOCK = threading.Lock()


def _load_store() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(settings.handoff_path().read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("tokens"), dict):
            return data["tokens"]
    except (FileNotFoundError, ValueError):
        pass
    return {}


def _save_store(tokens: dict[str, dict[str, Any]]) -> None:
    now = int(time.time())
    pruned = {k: v for k, v in tokens.items()
              if isinstance(v, dict) and int(v.get("exp") or 0) > now}
    path = settings.handoff_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"tokens": pruned}), encoding="utf-8")
    tmp.replace(path)


def _constant_time_lookup(tokens: dict[str, dict[str, Any]], token: str) -> dict[str, Any] | None:
    entry = None
    for key, value in tokens.items():
        if _hmac.compare_digest(key, token or ""):
            entry = value
    return entry


def issue(workspace_id: str, ttl_s: int = TOKEN_TTL_SECONDS) -> str | None:
    """Mint one opaque handoff token bound to a well-formed guest workspace.
    Returns None for malformed ids; raises nothing the caller must handle."""
    if not WORKSPACE_PATTERN.fullmatch(workspace_id or ""):
        return None
    token = secrets.token_urlsafe(32)
    with _LOCK:
        tokens = _load_store()
        tokens[token] = {"ws": workspace_id, "exp": int(time.time()) + max(30, ttl_s)}
        _save_store(tokens)
    return token


def redeem(token: str) -> str | None:
    """Validate and consume. Returns the bound workspace id on first use,
    else None. Identical None for unknown/expired/used so the endpoint
    cannot be probed."""
    with _LOCK:
        tokens = _load_store()
        entry = _constant_time_lookup(tokens, token or "")
        if not isinstance(entry, dict):
            return None
        workspace_id = entry.get("ws")
        exp = int(entry.get("exp") or 0)
        for key in list(tokens):
            if _hmac.compare_digest(key, token or ""):
                tokens.pop(key)
        _save_store(tokens)
    if exp < int(time.time()):
        return None
    if not isinstance(workspace_id, str) or not WORKSPACE_PATTERN.fullmatch(workspace_id):
        return None
    return workspace_id


def remaining_ttl(token: str) -> int | None:
    """Read-only expiry peek for operators issuing a URL. Never consumes."""
    with _LOCK:
        entry = _constant_time_lookup(_load_store(), token or "")
    if not isinstance(entry, dict):
        return None
    return max(0, int(entry.get("exp") or 0) - int(time.time()))
