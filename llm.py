import httpx

from config import OPENROUTER_API_KEY, OPENROUTER_MODEL


async def analyze(entries_text: str, system_prompt: str) -> str:
    """Send entries to OpenRouter with a given system prompt and return the analysis."""
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Publicaciones de hoy:\n\n{entries_text}",
                    },
                ],
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
