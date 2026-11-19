
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResumeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    created_at: datetime


class ResumeDetailResponse(ResumeResponse):
    content: str
