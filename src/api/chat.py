from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .drive_search import answer_drive_question
from .email_search import answer_email_question
from .unified_search import answer_question

app = FastAPI(title="Personal Brain API")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
    source: Literal["all", "email", "drive"] = "all"


@app.post("/chat")
async def chat(request: ChatRequest) -> dict:
    """Answer a question from all connected sources or one selected source."""
    if request.source == "drive":
        return answer_drive_question(request.question)
    if request.source == "email":
        return answer_email_question(request.question)
    return answer_question(request.question)


@app.post("/chat/drive")
async def drive_chat(request: ChatRequest) -> dict:
    """Convenience endpoint for a Drive-only question."""
    return answer_drive_question(request.question)


@app.post("/chat/all")
async def all_sources_chat(request: ChatRequest) -> dict:
    """Explicit cross-source endpoint: retrieve and reason over Gmail + Drive."""
    return answer_question(request.question)
