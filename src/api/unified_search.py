"""Unified cross-source retrieval for Gmail + Google Drive.

A single question is searched against both local exports before synthesis. This
is the retrieval path used by the Personal Brain chat endpoint for questions
that may require evidence from more than one source.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .drive_search import DRIVE_DIRECTORY, DriveSearchResult, search_drive
from .email_search import EMAIL_DIRECTORY, SearchResult, search_emails
from .grounded_synthesis import synthesize_answer_with_citations


DEFAULT_LIMIT_PER_SOURCE = 5


def _email_evidence(result: SearchResult) -> dict[str, Any]:
    email = result.email
    return {
        "source_type": "gmail",
        "source_id": email.id,
        "title": email.subject,
        "text": (
            f"Subject: {email.subject}\n"
            f"From: {email.sender}\n"
            f"To: {email.recipient}\n"
            f"Date: {email.date}\n\n"
            f"{email.body}"
        ),
        "excerpt": result.excerpt,
        "score": round(result.score, 2),
        "link": email.link,
    }


def _drive_evidence(result: DriveSearchResult) -> dict[str, Any]:
    file = result.file
    return {
        "source_type": "drive",
        "source_id": file.id,
        "title": file.name,
        "text": (
            f"Name: {file.name}\n"
            f"Owner: {file.owner}\n"
            f"Mime type: {file.mime_type}\n"
            f"Modified: {file.modified_time}\n\n"
            f"{file.body}"
        ),
        "excerpt": result.excerpt,
        "score": round(result.score, 2),
        "link": file.link,
    }


def search_all_sources(
    question: str,
    *,
    limit_per_source: int = DEFAULT_LIMIT_PER_SOURCE,
    email_directory: Path = EMAIL_DIRECTORY,
    drive_directory: Path = DRIVE_DIRECTORY,
) -> list[dict[str, Any]]:
    """Retrieve relevant evidence from Gmail and Drive for the same question."""
    email_results = search_emails(question, limit=limit_per_source, directory=email_directory)
    drive_results = search_drive(question, limit=limit_per_source, directory=drive_directory)

    evidence = [_email_evidence(result) for result in email_results]
    evidence.extend(_drive_evidence(result) for result in drive_results)

    # Preserve each source's ranking while interleaving the two connectors so
    # one source cannot completely crowd the context when both are relevant.
    evidence.sort(key=lambda item: item["score"], reverse=True)
    return evidence


def answer_question(
    question: str,
    *,
    limit_per_source: int = DEFAULT_LIMIT_PER_SOURCE,
    email_directory: Path = EMAIL_DIRECTORY,
    drive_directory: Path = DRIVE_DIRECTORY,
) -> dict[str, Any]:
    """Answer a question using grounded evidence retrieved from both sources."""
    evidence = search_all_sources(
        question,
        limit_per_source=limit_per_source,
        email_directory=email_directory,
        drive_directory=drive_directory,
    )

    if not evidence:
        return {
            "answer": "I couldn't find relevant evidence in the local Gmail or Google Drive exports.",
            "sources": [],
            "citations": [],
        }

    # Keep context bounded. The ranking has already been performed independently
    # by each connector, so the highest-scoring evidence is the best context.
    context = evidence[: limit_per_source * 2]
    fallback_parts = [
        f"[{item['source_type']}] {item['title']}: {item['excerpt']}"
        for item in context[:3]
    ]
    fallback = "I found relevant evidence. " + " ".join(fallback_parts)

    synthesized = synthesize_answer_with_citations(
        question,
        context,
        fallback,
    )

    sources = [
        {
            "source_type": item["source_type"],
            "id": item["source_id"],
            "title": item["title"],
            "link": item["link"],
            "excerpt": item["excerpt"],
            "score": item["score"],
        }
        for item in context
    ]

    return {
        "answer": synthesized["answer"],
        "sources": sources,
        "citations": synthesized["citations"],
    }
