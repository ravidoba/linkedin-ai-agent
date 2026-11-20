
from contextlib import asynccontextmanager

from app.api.routes import matching
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import health, jobs, auth, resumes, ai, apply, browser_stream
from app.core.config import get_settings

from app.services.apply_workflow import close_browser_session


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_browser_session()


app = FastAPI(
    lifespan=lifespan,
    title="LinkedIn AI Agent API",
    description="AI-powered job application assistant",
    version="1.0.0",
 swagger_ui_parameters={"supportedSubmitMethods": ["get", "post", "put", "delete", "patch"]},
)

# CORS: explicit origins only (wildcard is not allowed together with credentials).
_extra_origins = [
    o.strip()
    for o in get_settings().CORS_ALLOWED_ORIGINS.split(",")
    if o.strip() and o.strip() != "*"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", *_extra_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all API routes
app.include_router(jobs.router)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(resumes.router)
app.include_router(ai.router)
app.include_router(matching.router)
app.include_router(apply.router)
app.include_router(browser_stream.router)

@app.get("/")
async def root():
    return {
        "message": "LinkedIn AI Agent API is running",
        "status": "success",
    }
