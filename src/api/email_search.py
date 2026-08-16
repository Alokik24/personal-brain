"""Local, evidence-backed search over the Gmail markdown export.

This deliberately supplements semantic search with lexical ranking.  Email
questions often contain proper nouns, amounts, and status words where an exact
match is much more reliable than embeddings alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

import frontmatter

from .grounded_synthesis import synthesize_answer


EMAIL_DIRECTORY = Path(__file__).resolve().parents[2] / "brain-source" / "emails"
TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+(?=[A-Z•-])")
STOP_WORDS = {
    # General language
    "a", "about", "an", "and", "are", "did", "ever", "find", "for",
    "from", "have", "i", "is", "me", "my", "of", "on", "the", "to",
    "what", "with", "you", "your",

    # Generic entity words
    "email", "emails", "message", "messages",
    "file", "files", "document", "documents",
    "related", "thing", "things",

    # Query / presentation modifiers.
    # These describe the requested operation rather than the entity.
    "latest", "recent", "newest", "oldest", "current",
    "list", "show", "give", "tell", "which",
}


@dataclass(frozen=True)
class Email:
    """A normalized email record used by the chat API and UI."""

    id: str
    subject: str
    sender: str
    recipient: str
    date: str
    link: str
    body: str
    path: Path

    @property
    def searchable_text(self) -> str:
        return " ".join((self.subject, self.sender, self.recipient, self.body))


@dataclass(frozen=True)
class SearchResult:
    email: Email
    score: float
    excerpt: str


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text) if token.lower() not in STOP_WORDS]


def load_emails(directory: Path = EMAIL_DIRECTORY) -> list[Email]:
    """Load the local Gmail export; malformed files are skipped safely."""
    if not directory.exists():
        return []

    emails: list[Email] = []
    for path in directory.glob("*.md"):
        try:
            page = frontmatter.load(path)
            metadata = page.metadata
            if metadata.get("source") != "gmail":
                continue
            emails.append(
                Email(
                    id=str(metadata.get("gmail_id", path.stem)),
                    subject=str(metadata.get("subject", "[No subject]")),
                    sender=str(metadata.get("from", "[Unknown sender]")),
                    recipient=str(metadata.get("to", "[Unknown recipient]")),
                    date=str(metadata.get("date", "")),
                    link=str(metadata.get("gmail_link", "")),
                    body=page.content.strip(),
                    path=path,
                )
            )
        except (OSError, ValueError, TypeError):
            continue
    return emails


def _score(query_tokens: list[str], email: Email) -> float:
    """Score only candidates with meaningful query-term coverage."""

    if not query_tokens:
        return 0.0

    unique_tokens = set(query_tokens)
    subject = email.subject.lower()
    sender = email.sender.lower()
    text = email.searchable_text.lower()

    matched = {
        token
        for token in unique_tokens
        if token in text
    }

    if not matched:
        return 0.0

    coverage = len(matched) / len(unique_tokens)

    # For multi-term queries, require most of the actual query to
    # occur in the email. This prevents:
    #
    # "narendra modi" -> unrelated email containing only "modi"
    #
    # from being considered relevant.
    if len(unique_tokens) >= 2 and coverage < 0.75:
        return 0.0

    score = coverage * 10

    # Exact matches in high-signal fields are stronger than body matches.
    score += sum(6 for token in unique_tokens if token in subject)
    score += sum(4 for token in unique_tokens if token in sender)

    # Exact multi-word phrase gets a substantial boost.
    query_phrase = " ".join(query_tokens)

    if len(query_tokens) >= 2 and query_phrase in text:
        score += 10

    # A one-word query must have a strong field match rather than
    # merely appearing somewhere in a long email body.
    if len(unique_tokens) == 1 and not (
        query_tokens[0] in subject
        or query_tokens[0] in sender
    ):
        return 0.0

    return score

def _best_excerpt(email: Email, query_tokens: Iterable[str]) -> str:
    tokens = set(query_tokens)
    # Gmail's quoted-printable/plain-text exports often wrap a sentence across
    # physical lines. Join those lines before selecting the evidence sentence.
    normalized_body = re.sub(r"\s*\n\s*", " ", email.body)
    sentences = [part.strip(" -•\t") for part in SENTENCE_RE.split(normalized_body) if part.strip()]
    if not sentences:
        return "No message body was available."

    def sentence_score(sentence: str) -> tuple[int, int]:
        lowered = sentence.lower()
        return (sum(token in lowered for token in tokens), -len(sentence))

    best = max(sentences, key=sentence_score)
    return re.sub(r"\s+", " ", best)[:500]


def search_emails(question: str, limit: int = 5, directory: Path = EMAIL_DIRECTORY) -> list[SearchResult]:
    """Rank local Gmail messages for a natural-language question."""
    query_tokens = _tokens(question)
    if not query_tokens:
        return []
    results = [
        SearchResult(email=email, score=_score(query_tokens, email), excerpt=_best_excerpt(email, query_tokens))
        for email in load_emails(directory)
    ]
    return sorted((item for item in results if item.score > 0), key=lambda item: item.score, reverse=True)[:limit]


def answer_email_question(
    question: str,
    directory: Path = EMAIL_DIRECTORY,
) -> dict:
    """Answer a question using locally retrieved Gmail evidence."""
    results = search_emails(question, directory=directory)

    if not results:
        return {
            "answer": "I couldn't find an email that matches that question in the local Gmail export.",
            "sources": [],
        }

    top = results[0]

    if len(results) == 1 or top.score >= results[1].score + 4:
        source_results = results[:1]
        fallback = top.excerpt
    else:
        source_results = results[:3]
        fallback = "I found several relevant emails."

    answer = synthesize_answer(
        question,
        (
            f"Subject: {result.email.subject}\n"
            f"From: {result.email.sender}\n"
            f"Date: {result.email.date}\n\n"
            f"{result.email.body}"
            for result in source_results
        ),
        fallback,
        "Gmail",
    )

    return {
        "answer": answer,
        "sources": [
            {
                "id": result.email.id,
                "subject": result.email.subject,
                "from": result.email.sender,
                "date": result.email.date,
                "link": result.email.link,
                "excerpt": result.excerpt,
                "score": round(result.score, 2),
            }
            for result in source_results
        ],
    }