
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobCreate(BaseModel):
    linkedin_job_id: str
    title: str
    company: str
    location: str | None = None
    description: str | None = None
    job_url: str | None = None


class JobResponse(JobCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    match_score: float | None
    status: str
    created_at: datetime
