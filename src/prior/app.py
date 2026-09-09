from __future__ import annotations

import re
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from prior import auth, service
from prior.auth import AuthError
from prior.memory import MEMORY_UNAVAILABLE, MemoryUnavailable
from prior.providers.base import ProviderError
from prior.settings import (
    acp_enabled,
    email_configured,
    google_configured,
    local_provider_enabled,
    missing_virtuals_credentials,
)

STATIC = Path(__file__).resolve().parent / "static"
COOKIE = "prior_workspace"
WORKSPACE_PATTERN = re.compile(r"^ws_[a-f0-9]{16}$")
app = FastAPI(title="PRIOR", version="0.1.0")


class SpecifyIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class LessonIn(BaseModel):
    action: str
    requirement: str | None = None
    issue: str | None = None


class EmailStartIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class EmailVerifyIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=4, max_length=32)


def _workspace(request: Request, response: Response) -> str:
    current = request.cookies.get(COOKIE)
    if current and WORKSPACE_PATTERN.fullmatch(current):
        if auth.get_store().workspace_owner(current) is None:
            return current
    workspace_id = "ws_" + secrets.token_hex(8)
    response.set_cookie(
        COOKIE,
        workspace_id,
        **auth.workspace_cookie_kwargs(),
    )
    return workspace_id


def _identity(request: Request, response: Response) -> tuple[str, dict | None]:
    """Effective workspace + account (if authenticated). Guest behavior is
    byte-for-byte identical to the historical workspace-cookie path."""
    return auth.resolve_effective_workspace(request, response, _workspace)


@app.get("/healthz")
@app.get("/api/health")
def health() -> dict:
    from prior.doctor import snapshot

    return snapshot()



@app.post("/api/jobs")
def specify_job(payload: SpecifyIn, request: Request, response: Response) -> dict:
    workspace_id, _ = _identity(request, response)
    record = service.specify(workspace_id, payload.text)
    return record.to_dict()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, request: Request, response: Response) -> dict:
    workspace_id, _ = _identity(request, response)
    try:
        record = service.refresh(workspace_id, job_id)
        body = record.to_dict()
        from prior import hiring as hiring_mod

        body["prior_lifecycle"] = hiring_mod.describe_lifecycle(record)
        return body
    except ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/jobs/{job_id}/hire")
def hire_job(job_id: str, request: Request, response: Response) -> dict:
    """RETIRED historical hire endpoint. Always 410 Gone.

    This route must never perform an ACP write: it cannot reach
    service.hire, provider.create_job, or any write bridge command. The
    normal consumer flow uses /hire/prepare (read-only selection plus
    confirmation) followed by /hire/execute (single confirmed write).
    """
    raise HTTPException(
        410,
        "This hire endpoint has been retired. "
        "Use /hire/prepare followed by /hire/execute.",
    )


@app.post("/api/jobs/{job_id}/hire/prepare")
def hire_prepare(job_id: str, request: Request, response: Response) -> dict:
    """READ-ONLY dynamic prepare: live marketplace selection frozen as a
    HirePlan, returned with user-facing confirmation content. No ACP write."""
    from prior import hiring as hiring_mod
    from prior.marketplace import NoCompatibleProvider

    workspace_id, _ = _identity(request, response)
    try:
        plan_dict = service.prepare_hire(workspace_id, job_id)
        plan = hiring_mod.HirePlan.from_dict(plan_dict)
        record = service.refresh(workspace_id, job_id)
        return {"job": record.to_dict(),
                "hire_plan": hiring_mod.plan_presentation(plan)}
    except MemoryUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except NoCompatibleProvider as exc:
        raise HTTPException(400, str(exc)) from exc
    except hiring_mod.AmbiguousHireError as exc:
        raise HTTPException(409, str(exc)) from exc
    except hiring_mod.HireError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs/{job_id}/hire/execute")
def hire_execute(job_id: str, request: Request, response: Response) -> dict:
    """WRITE: execute the previously confirmed HirePlan exactly once."""
    from prior import hiring as hiring_mod
    from prior import jobs as jobs_mod

    workspace_id, _ = _identity(request, response)
    try:
        return service.execute_hire(workspace_id, job_id).to_dict()
    except MemoryUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except hiring_mod.AmbiguousHireError as exc:
        raise HTTPException(409, str(exc)) from exc
    except jobs_mod.HireConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except hiring_mod.HireError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ProviderError as exc:
        status = 403 if "disabled by server configuration" in str(exc) else 503
        raise HTTPException(status, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs/{job_id}/fund/prepare")
def fund_prepare(job_id: str, request: Request, response: Response) -> dict:
    """READ-ONLY funding intent: observe the live seller budget and freeze
    what an explicit user confirmation would fund. No ACP write."""
    from prior import hiring as hiring_mod

    workspace_id, _ = _identity(request, response)
    try:
        plan = service.prepare_fund(workspace_id, job_id)
        record = service.refresh(workspace_id, job_id)
        return {"job": record.to_dict(), "fund_plan": plan}
    except MemoryUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except hiring_mod.AmbiguousHireError as exc:
        raise HTTPException(409, str(exc)) from exc
    except hiring_mod.HireError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs/{job_id}/fund/execute")
def fund_execute(job_id: str, request: Request, response: Response) -> dict:
    """WRITE: fund exactly the previously confirmed funding intent, once."""
    from prior import hiring as hiring_mod
    from prior import jobs as jobs_mod

    workspace_id, _ = _identity(request, response)
    try:
        return service.execute_fund(workspace_id, job_id).to_dict()
    except MemoryUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except hiring_mod.AmbiguousHireError as exc:
        raise HTTPException(409, str(exc)) from exc
    except jobs_mod.FundConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except hiring_mod.HireError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ProviderError as exc:
        status = 403 if "disabled by server configuration" in str(exc) else 503
        raise HTTPException(status, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs/{job_id}/accept")
def accept_job(job_id: str, request: Request, response: Response) -> dict:
    workspace_id, _ = _identity(request, response)
    try:
        return service.accept(workspace_id, job_id).to_dict()
    except ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs/{job_id}/reject")
def reject_job(payload: RejectIn, job_id: str, request: Request, response: Response) -> dict:
    workspace_id, _ = _identity(request, response)
    try:
        return service.reject(workspace_id, job_id, payload.reason).to_dict()
    except ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs/{job_id}/lessons")
def lesson_decision(payload: LessonIn, job_id: str, request: Request, response: Response) -> dict:
    workspace_id, _ = _identity(request, response)
    try:
        return service.decide_lesson(
            workspace_id,
            job_id,
            payload.action,
            payload.requirement,
            payload.issue,
        ).to_dict()
    except MemoryUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/memory")
def memory(request: Request, response: Response) -> dict:
    workspace_id, _ = _identity(request, response)
    return service.memory_view(workspace_id)


@app.post("/api/memory/{lesson_id}/disable")
def disable_memory(lesson_id: str, request: Request, response: Response) -> dict:
    workspace_id, _ = _identity(request, response)
    try:
        return service.retire_lesson(workspace_id, lesson_id)
    except MemoryUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/base/verify")
def verify_base(network: str = "mainnet") -> dict:
    from prior.base_action import read_b20_factory

    url = "https://sepolia.base.org" if network == "sepolia" else "https://mainnet.base.org"
    try:
        data = read_b20_factory(url=url)
        data["network_name"] = "Base Sepolia" if network == "sepolia" else "Base Mainnet"
        return data
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Base RPC read error: {exc}") from exc


@app.get("/api/workspace")
def workspace(request: Request, response: Response) -> dict:
    workspace_id, account = _identity(request, response)
    local = local_provider_enabled() and not acp_enabled()
    virtuals = acp_enabled()
    if virtuals:
        hire_mode = "virtuals"
        provider_name = None
        network = "Virtuals ACP"
    elif local:
        hire_mode = "local"
        provider_name = "PRIOR Local Research Agent"
        network = "Local"
    else:
        hire_mode = "none"
        provider_name = None
        network = None
    return {
        "workspace_id": workspace_id,
        "hire_mode": hire_mode,
        "provider_name": provider_name,
        "network": network,
        "local_provider": local,
        "acp_enabled": virtuals,
        "virtuals_credentials_missing": missing_virtuals_credentials(),
        "memory_unavailable_copy": MEMORY_UNAVAILABLE,
        "account": auth.account_view(account) if account else None,
        "pending_guest_workspace": _pending_guest(request, workspace_id, account),
        "google_configured": google_configured(),
        "email_configured": email_configured(),
    }


def _pending_guest(request: Request, workspace_id: str, account: dict | None) -> str | None:
    """An unrelated guest workspace preserved for a future explicit decision.
    Never merged automatically."""
    if not account:
        return None
    guest = request.cookies.get(auth.WORKSPACE_COOKIE)
    if guest and guest != workspace_id and WORKSPACE_PATTERN.fullmatch(guest):
        return guest
    return None


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    client = request.client
    return str(getattr(client, "host", "unknown"))[:64]


def _set_session(response: Response, token: str) -> None:
    response.set_cookie(auth.SESSION_COOKIE, token, **auth.session_cookie_kwargs())


def _clear_session(response: Response) -> None:
    response.delete_cookie(auth.SESSION_COOKIE, path="/")


def _login_response(
    response: Response, result: dict, request: Request
) -> dict:
    from prior import settings as settings_mod

    store = auth.get_store()
    account = result["account"]
    guest_cookie = request.cookies.get(auth.WORKSPACE_COOKIE)
    guest_ws = (
        guest_cookie
        if guest_cookie and WORKSPACE_PATTERN.fullmatch(guest_cookie)
        else str(result["guest_workspace"])
    )
    effective_ws, claimed, preserved = auth.claim_or_resolve(
        store, str(account["id"]), guest_ws
    )
    token = store.create_session(str(account["id"]), settings_mod.session_ttl_seconds())
    _set_session(response, token)
    if preserved:
        response.set_cookie(
            COOKIE, preserved, **auth.workspace_cookie_kwargs()
        )
    else:
        auth.mint_guest_workspace(store, response)
    body = {
        "authenticated": True,
        "account": auth.account_view(account),
        "workspace_id": effective_ws,
        "claimed": claimed,
        "provider": result["provider"],
    }
    if preserved:
        body["pending_guest_workspace"] = preserved
    return body


@app.get("/api/auth/me")
def auth_me(request: Request, response: Response) -> dict:
    workspace_id, account = _identity(request, response)
    body: dict = {
        "authenticated": account is not None,
        "workspace_id": workspace_id,
        "account": auth.account_view(account) if account else None,
        "google_configured": google_configured(),
        "email_configured": email_configured(),
    }
    pending = _pending_guest(request, workspace_id, account)
    if pending:
        body["pending_guest_workspace"] = pending
    return body


@app.get("/api/auth/google/start")
def auth_google_start(request: Request, response: Response):
    guest = request.cookies.get(auth.WORKSPACE_COOKIE)
    minted: str | None = None
    store = auth.get_store()
    if not (
        guest
        and WORKSPACE_PATTERN.fullmatch(guest)
        and store.workspace_owner(guest) is None
    ):
        minted = "ws_" + secrets.token_hex(8)
        guest = minted
        store.ensure_workspace_row(guest)
    try:
        target = auth.start_google_login(guest, _client_ip(request))
    except AuthError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    redirect = RedirectResponse(target, status_code=307)
    if minted:
        redirect.set_cookie(COOKIE, minted, **auth.workspace_cookie_kwargs())
    return redirect


@app.get("/api/auth/google/callback")
def auth_google_callback(
    request: Request, response: Response, code: str = "", state: str = ""
) -> Response:
    if request.query_params.get("error"):
        return RedirectResponse("/app?auth=cancelled", status_code=302)
    try:
        result = auth.finish_google_login(code, state)
    except AuthError as exc:
        reason = "expired" if exc.status == 400 else "provider"
        return RedirectResponse(f"/app?auth=error&reason={reason}", status_code=302)
    redirect = RedirectResponse("/app?auth=signed-in", status_code=302)
    _login_response(redirect, result, request)
    return redirect


@app.post("/api/auth/email/start")
def auth_email_start(payload: EmailStartIn, request: Request, response: Response) -> dict:
    _workspace(request, response)
    guest = request.cookies.get(auth.WORKSPACE_COOKIE) or ""
    try:
        return auth.start_email_login(payload.email, guest, _client_ip(request))
    except AuthError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@app.post("/api/auth/email/verify")
def auth_email_verify(payload: EmailVerifyIn, request: Request, response: Response) -> dict:
    try:
        result = auth.verify_email_code(payload.email, payload.code)
    except AuthError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return _login_response(response, result, request)


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response) -> dict:
    store = auth.get_store()
    auth.revoke_presented_sessions(request, store)
    _clear_session(response)
    current = request.cookies.get(auth.WORKSPACE_COOKIE)
    if current and store.workspace_owner(current) is not None:
        auth.mint_guest_workspace(store, response)
    return {"ok": True}


if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(
        STATIC / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/app")
def app_page() -> FileResponse:
    return FileResponse(
        STATIC / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/memory")
def memory_page() -> FileResponse:
    return FileResponse(
        STATIC / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/proof")
def proof_page() -> FileResponse:
    return FileResponse(
        STATIC / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
