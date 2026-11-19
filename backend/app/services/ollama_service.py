
import httpx

from app.core.config import get_settings


async def ask_ollama(prompt: str) -> str:
    settings = get_settings()

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat",
            json={
                "model": "qwen3:4b-instruct-2507-q4_K_M",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a job matching assistant. "
                            "Return only the requested answer. "
                            "Be concise and accurate. "
                            "Never invent candidate qualifications."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                "stream": False,
                "think": False,
                "options": {
                    "temperature": 0,
                    "num_predict": 1024,
                },
                "keep_alive": "30m",
            },
        )

        response.raise_for_status()
        data = response.json()

        return data["message"]["content"].strip()
