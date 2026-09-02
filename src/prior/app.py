from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from prior import service
from prior.memory import MEMORY_UNAVAILABLE, MemoryUnavailable
from prior.providers.base import ProviderError
from prior.settings import acp_enabled, local_provider_enabled, missing_virtuals_credentials

STATIC = Path(__file__).resolve().parent / "static"
COOKIE = "prior_workspace"
app = FastAPI(title="PRIOR", version="0.1.0")


class SpecifyIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class LessonIn(BaseModel):
    action: str
    requirement: str | None = None
    issue: str | None = None


def _workspace(request: Request, response: Response) -> str:
    current = request.cookies.get(COOKIE)
    if current and current.startswith("ws_") and ".." not in current:
        return current
    workspace_id = "ws_" + secrets.token_hex(8)
    response.set_cookie(
        COOKIE,
        workspace_id,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 400,
    )
    return workspace_id


@app.get("/api/health")
def health() -> dict:
    from prior.doctor import snapshot

    return snapshot()


@app.post("/api/jobs")
def specify_job(payload: SpecifyIn, request: Request, response: Response) -> dict:
    workspace_id = _workspace(request, response)
    record = service.specify(workspace_id, payload.text)
    return record.to_dict()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, request: Request, response: Response) -> dict:
    workspace_id = _workspace(request, response)
    try:
        return service.refresh(workspace_id, job_id).to_dict()
    except ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/jobs/{job_id}/hire")
def hire_job(job_id: str, request: Request, response: Response) -> dict:
    workspace_id = _workspace(request, response)
    try:
        return service.hire(workspace_id, job_id).to_dict()
    except MemoryUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs/{job_id}/accept")
def accept_job(job_id: str, request: Request, response: Response) -> dict:
    workspace_id = _workspace(request, response)
    try:
        return service.accept(workspace_id, job_id).to_dict()
    except ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs/{job_id}/reject")
def reject_job(payload: RejectIn, job_id: str, request: Request, response: Response) -> dict:
    workspace_id = _workspace(request, response)
    try:
        return service.reject(workspace_id, job_id, payload.reason).to_dict()
    except ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs/{job_id}/lessons")
def lesson_decision(payload: LessonIn, job_id: str, request: Request, response: Response) -> dict:
    workspace_id = _workspace(request, response)
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
    workspace_id = _workspace(request, response)
    return service.memory_view(workspace_id)


@app.post("/api/memory/{lesson_id}/disable")
def disable_memory(lesson_id: str, request: Request, response: Response) -> dict:
    workspace_id = _workspace(request, response)
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
    workspace_id = _workspace(request, response)
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
    }


if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/memory")
def memory_page() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/proof")
def proof_page() -> FileResponse:
    return FileResponse(STATIC / "index.html")
