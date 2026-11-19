
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import httpx

from app.core.dependencies import get_current_user
from app.services.ollama_service import ask_ollama

router = APIRouter(
    prefix="/ai",
    tags=["AI"],
    dependencies=[Depends(get_current_user)],
)


class AIRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=10000)


class AIResponse(BaseModel):
    response: str


@router.post("/chat", response_model=AIResponse)
async def chat_with_ai(request: AIRequest):
    try:
        result = await ask_ollama(request.prompt)
        return AIResponse(response=result)
    except httpx.HTTPError:
        raise HTTPException(
            status_code=503,
            detail="Ollama service is unavailable",
        )
