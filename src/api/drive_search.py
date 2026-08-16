"""Local, evidence-backed search over exported Google Drive markdown pages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import frontmatter

from .email_search import _tokens
from .grounded_synthesis import synthesize_answer


DRIVE_DIRECTORY = Path(__file__).resolve().parents[2] / "brain-source" / "drives"
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    mime_type: str
    modified_time: str
    link: str
    owner: str
    body: str

    @property
    def searchable_text(self) -> str:
        return " ".join((self.name, self.mime_type, self.owner, self.body))


@dataclass(frozen=True)
class DriveSearchResult:
    file: DriveFile
    score: float
    excerpt: str


def load_drive_files(directory: Path = DRIVE_DIRECTORY) -> list[DriveFile]:
    """Load valid Drive markdown exports, ignoring raw downloaded PDFs."""
    if not directory.exists():
        return []
    records: list[DriveFile] = []
    for path in directory.glob("*.md"):
        try:
            page = frontmatter.load(path)
            metadata = page.metadata
            records.append(
                DriveFile(
                    id=path.stem,
                    name=str(metadata.get("name", path.stem)),
                    mime_type=str(metadata.get("mime_type", "unknown")),
                    modified_time=str(metadata.get("modified_time", "")),
                    link=str(metadata.get("drive_link", "")),
                    owner=str(metadata.get("owner", "unknown")),
                    body=page.content.strip(),
                )
            )
        except (OSError, ValueError, TypeError):
            continue
    return records


def _excerpt(file: DriveFile, tokens: set[str], question: str) -> str:
    content_lines = [
        line.strip()
        for line in file.body.splitlines()
        if line.strip() and not line.startswith(("#", "-", "*"))
    ]
    content = "\n".join(content_lines)

    sentences = [
        part.strip(" -•\t")
        for part in SENTENCE_RE.split(content)
        if len(part.strip(" -•\t")) >= 30
    ]

    if not sentences:
        return "No exported text is available for this file."

    best = max(
        sentences,
        key=lambda sentence: (
            sum(token in sentence.lower() for token in tokens),
            len(sentence),
        ),
    )

    return re.sub(r"\s+", " ", best)[:500]

def search_drive(
    question: str,
    limit: int = 5,
    directory: Path = DRIVE_DIRECTORY,
) -> list[DriveSearchResult]:
    """Rank Drive files while rejecting weak partial matches."""

    query_tokens = _tokens(question)

    if not query_tokens:
        return []

    unique_tokens = set(query_tokens)
    results: list[DriveSearchResult] = []

    for file in load_drive_files(directory):
        text = file.searchable_text.lower()
        name = file.name.lower()
        owner = file.owner.lower()

        matched = {
            token
            for token in unique_tokens
            if token in text
        }

        if not matched:
            continue

        coverage = len(matched) / len(unique_tokens)

        # Don't return files that only match one incidental word.
        if len(unique_tokens) >= 2 and coverage < 0.75:
            continue

        score = coverage * 10

        # File names are high-signal.
        score += sum(
            6 for token in unique_tokens
            if token in name
        )

        # Owner is weaker evidence.
        score += sum(
            2 for token in unique_tokens
            if token in owner
        )

        # Exact phrase is very strong evidence.
        query_phrase = " ".join(query_tokens)

        if len(query_tokens) >= 2 and query_phrase in text:
            score += 10

        # For a one-word query, accept either a filename or content match.
        # The filename still receives a stronger score above.
        if len(unique_tokens) == 1:
            token = query_tokens[0]
            if token not in name and token not in text:
                continue

        results.append(
            DriveSearchResult(
                file,
                score,
                _excerpt(file, unique_tokens, question),
            )
        )

    return sorted(
        results,
        key=lambda result: result.score,
        reverse=True,
    )[:limit]

def answer_drive_question(
    question: str,
    directory: Path = DRIVE_DIRECTORY,
) -> dict:
    """Answer a question using locally retrieved Drive evidence."""
    results = search_drive(question, directory=directory)

    if not results:
        return {
            "answer": "I couldn't find a Drive file that matches that question in the local export.",
            "sources": [],
        }

    top = results[0]

    if len(results) == 1 or top.score >= results[1].score + 4:
        source_results = results[:1]
        fallback = top.excerpt
    else:
        source_results = results[:3]
        fallback = "I found several relevant Drive files."

    answer = synthesize_answer(
        question,
        (
            f"Name: {result.file.name}\n"
            f"Owner: {result.file.owner}\n"
            f"Modified: {result.file.modified_time}\n\n"
            f"{result.file.body}"
            for result in source_results
        ),
        fallback,
        "Google Drive",
    )

    return {
        "answer": answer,
        "sources": [
            {
                "id": result.file.id,
                "name": result.file.name,
                "mime_type": result.file.mime_type,
                "modified_time": result.file.modified_time,
                "owner": result.file.owner,
                "link": result.file.link,
                "excerpt": result.excerpt,
                "score": round(result.score, 2),
            }
            for result in source_results
        ],
    }