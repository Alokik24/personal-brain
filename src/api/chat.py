from pydantic import BaseModel, Field
from fastapi import FastAPI

from .email_search import answer_email_question

app = FastAPI(title="Personal Brain API")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)


@app.post("/chat")
async def chat(request: ChatRequest) -> dict:
    """Answer a Tier-1 Gmail question from locally ingested mail only."""
    return answer_email_question(request.question)
