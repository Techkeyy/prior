from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from prior import service
from prior.acp import AcpUnavailable
from prior.memory import MEMORY_UNAVAILABLE, MemoryUnavailable
from prior.settings import local_provider_enabled

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
        return service._owned(workspace_id, job_id).to_dict()
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/jobs/{job_id}/hire")
def hire_job(job_id: str, request: Request, response: Response) -> dict:
    workspace_id = _workspace(request, response)
    try:
        return service.hire(workspace_id, job_id).to_dict()
    except MemoryUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except AcpUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs/{job_id}/accept")
def accept_job(job_id: str, request: Request, response: Response) -> dict:
    workspace_id = _workspace(request, response)
    try:
        return service.accept(workspace_id, job_id).to_dict()
    except AcpUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs/{job_id}/reject")
def reject_job(payload: RejectIn, job_id: str, request: Request, response: Response) -> dict:
    workspace_id = _workspace(request, response)
    try:
        return service.reject(workspace_id, job_id, payload.reason).to_dict()
    except AcpUnavailable as exc:
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


@app.get("/api/workspace")
def workspace(request: Request, response: Response) -> dict:
    workspace_id = _workspace(request, response)
    return {
        "workspace_id": workspace_id,
        "local_provider": local_provider_enabled(),
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
