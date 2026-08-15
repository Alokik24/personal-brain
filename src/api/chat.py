from typing import Literal

from pydantic import BaseModel, Field
from fastapi import FastAPI

from .drive_search import answer_drive_question
from .email_search import answer_email_question

app = FastAPI(title="Personal Brain API")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
    source: Literal["email", "drive"] = "email"


@app.post("/chat")
async def chat(request: ChatRequest) -> dict:
    """Answer a question from the selected local data source."""
    if request.source == "drive":
        return answer_drive_question(request.question)
    return answer_email_question(request.question)


@app.post("/chat/drive")
async def drive_chat(request: ChatRequest) -> dict:
    """Convenience endpoint for a Drive-only question."""
    return answer_drive_question(request.question)
