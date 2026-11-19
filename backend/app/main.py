from app.api.routes import matching
from fastapi import FastAPI
from app.api.routes import health, jobs, auth, resumes, ai

app = FastAPI(
    title="LinkedIn AI Agent API",
    description="AI-powered job application assistant",
    version="1.0.0",
 swagger_ui_parameters={"supportedSubmitMethods": ["get", "post", "put", "delete", "patch"]},
)

# Register all API routes
app.include_router(jobs.router)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(resumes.router)
app.include_router(ai.router)
app.include_router(matching.router)

@app.get("/")
async def root():
    return {
        "message": "LinkedIn AI Agent API is running",
        "status": "success",
    }
