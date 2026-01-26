"""
Copilot App Factory - FastAPI Backend

This is the main API server that handles site generation requests.
Cloud-agnostic implementation using GitHub Copilot SDK.
"""

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Callable, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from site_builder import build_site, get_job, BuildStatus, BuildJob, create_job


# =============================================================================
# Build Invoker - Abstraction for local vs cloud execution
# =============================================================================
# In production, this is overridden by cloud_handler.py
# For local dev, we use a simple thread-based approach

_build_invoker: Optional[Callable[[str, str], None]] = None


def set_build_invoker(invoker: Callable[[str, str], None]):
    """Set the build invoker function (called by cloud_handler.py in production)."""
    global _build_invoker
    _build_invoker = invoker


def _local_build_invoker(job_id: str, description: str):
    """Local development build invoker - runs in a thread."""
    import threading

    def run_sync():
        asyncio.run(build_site(
            job_id=job_id,
            description=description,
            deploy_func=None  # No deploy in local dev
        ))

    thread = threading.Thread(target=run_sync)
    thread.start()


# Configuration from environment
API_KEY = os.getenv("API_KEY")
APPS_BASE_URL = os.getenv("APPS_BASE_URL", "")


# Rate limiting
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    print("Copilot App Factory starting up...")
    yield
    print("Copilot App Factory shutting down...")


# Initialize FastAPI
app = FastAPI(
    title="Copilot App Factory",
    description="AI-powered static site generator using GitHub Copilot SDK",
    version="1.0.0",
    lifespan=lifespan,
)

# Add rate limit error handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": "Rate limit exceeded. Please try again later."}
    )

app.state.limiter = limiter


# CORS middleware - production origins only
# Local dev uses proxy via vite.config.js, no CORS needed
ALLOWED_ORIGINS = [
    "https://wirier.com",
    "https://www.wirier.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)


# API Key authentication middleware
@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    """Verify API key for protected endpoints."""
    # Allow public endpoints
    public_paths = ["/", "/health", "/api/health"]
    if request.url.path in public_paths:
        return await call_next(request)

    # Allow OPTIONS requests (CORS preflight)
    if request.method == "OPTIONS":
        return await call_next(request)

    # Check API key (loaded from environment variable)
    request_key = request.headers.get("X-API-Key")
    if API_KEY and request_key != API_KEY:
        return JSONResponse(
            status_code=401,
            content={"error": "Unauthorized - Invalid or missing API key"}
        )

    return await call_next(request)


# Request/Response models
class BuildRequest(BaseModel):
    """Request to build a new site."""
    description: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Description of the site to generate"
    )


class BuildResponse(BaseModel):
    """Response after initiating a build."""
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    """Detailed status of a build job."""
    job_id: str
    status: str
    progress: int
    message: str
    site_url: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str
    logs: list[str] = []


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    version: str


# API Routes
@app.get("/", response_model=HealthResponse)
@app.get("/health", response_model=HealthResponse)
@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0"
    )


@app.post("/api/build", response_model=BuildResponse)
@limiter.limit("5/minute")
async def create_build(
    request: Request,
    build_request: BuildRequest
):
    """
    Create a new site build job using GitHub Copilot SDK.

    This endpoint initiates an async build process. Use the returned job_id
    to poll for status updates.
    """
    # Generate unique job ID
    job_id = str(uuid.uuid4())[:8]

    # Create job record BEFORE invoking async build
    create_job(job_id, build_request.description)

    # Invoke build (uses cloud invoker in production, thread in dev)
    invoker = _build_invoker or _local_build_invoker
    invoker(job_id, build_request.description)

    return BuildResponse(
        job_id=job_id,
        status="pending",
        message=f"Build job {job_id} created. Poll /api/status/{job_id} for updates."
    )


@app.get("/api/status/{job_id}", response_model=JobStatusResponse)
@limiter.limit("60/minute")  # Allow frequent polling but prevent abuse
async def get_build_status(request: Request, job_id: str):
    """
    Get the status of a build job.

    Returns detailed status including progress percentage, current step,
    and the final site URL when complete.
    """
    job = get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found"
        )

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status.value,
        progress=job.progress,
        message=job.message,
        site_url=job.site_url,
        error=job.error,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        logs=job.logs[-20:] if job.logs else []  # Return last 20 log entries
    )


@app.get("/api/jobs")
@limiter.limit("30/minute")  # Prevent enumeration attacks
async def list_jobs(request: Request, limit: int = 10, status: Optional[str] = None):
    """
    List recent build jobs.

    Optionally filter by status (pending, running, completed, failed).
    """
    # Cap limit to prevent abuse
    limit = min(limit, 50)

    from site_builder import _jobs

    jobs = list(_jobs.values())

    # Filter by status if provided
    if status:
        try:
            filter_status = BuildStatus(status)
            jobs = [j for j in jobs if j.status == filter_status]
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Valid values: pending, running, completed, failed"
            )

    # Sort by created_at descending and limit
    jobs = sorted(jobs, key=lambda j: j.created_at, reverse=True)[:limit]

    return {
        "jobs": [
            {
                "job_id": j.job_id,
                "status": j.status.value,
                "progress": j.progress,
                "message": j.message,
                "site_url": j.site_url,
                "created_at": j.created_at.isoformat(),
            }
            for j in jobs
        ],
        "total": len(jobs)
    }


# Local development server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
