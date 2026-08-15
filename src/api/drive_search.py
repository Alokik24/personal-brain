"""Local, evidence-backed search over exported Google Drive markdown pages."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import csv
import io
import re

import frontmatter

from .email_search import _tokens
from .grounded_synthesis import synthesize_answer


DRIVE_DIRECTORY = Path(__file__).resolve().parents[2] / "brain-source" / "drives"
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
AGGREGATION_WORDS = {"total", "sum", "amount", "much", "many", "all"}


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
    # The markdown export begins with a title and a metadata bullet list. Those
    # are useful sources, but answering with only a filename is not useful.
    # Select from the exported file content instead.
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
    if re.search(r"\b(about|describe|summary|summarize)\b", question, re.IGNORECASE):
        return re.sub(r"\s+", " ", sentences[0])[:500]
    best = max(sentences, key=lambda sentence: (sum(token in sentence.lower() for token in tokens), len(sentence)))
    return re.sub(r"\s+", " ", best)[:500]


def search_drive(question: str, limit: int = 5, directory: Path = DRIVE_DIRECTORY) -> list[DriveSearchResult]:
    """Rank Drive files, strongly preferring exact matches in their names."""
    query_tokens = _tokens(question)
    if not query_tokens:
        return []
    results: list[DriveSearchResult] = []
    for file in load_drive_files(directory):
        text = file.searchable_text.lower()
        matched = [token for token in query_tokens if token in text]
        if not matched:
            continue
        coverage = len(set(matched)) / len(set(query_tokens))
        score = coverage * 10 + len(matched)
        score += sum(6 for token in query_tokens if token in file.name.lower())
        score += sum(2 for token in query_tokens if token in file.owner.lower())
        results.append(DriveSearchResult(file, score, _excerpt(file, set(query_tokens), question)))
    return sorted(results, key=lambda result: result.score, reverse=True)[:limit]


def _csv_rows(file: DriveFile) -> list[dict[str, str]]:
    """Read the CSV portion of a Google Sheets markdown export, if present."""
    lines = file.body.splitlines()
    header_index = next(
        (index for index, line in enumerate(lines) if "," in line and "amount" in line.lower()),
        None,
    )
    if header_index is None:
        return []
    return list(csv.DictReader(io.StringIO("\n".join(lines[header_index:]))))


def _money(value: str) -> tuple[str, Decimal] | None:
    cleaned = value.strip().replace(",", "")
    match = re.fullmatch(r"(?P<currency>[^0-9.\-]*)(?P<amount>-?[0-9]+(?:\.[0-9]+)?)", cleaned)
    if not match:
        return None
    try:
        return match.group("currency") or "$", Decimal(match.group("amount"))
    except InvalidOperation:
        return None


def _total_answer(question: str, results: list[DriveSearchResult]) -> str | None:
    """Answer simple total/sum questions over exported Google Sheets rows."""
    if not (set(_tokens(question)) & AGGREGATION_WORDS):
        return None
    match_terms = set(_tokens(question)) - AGGREGATION_WORDS
    if not match_terms:
        return None

    totals: dict[str, Decimal] = {}
    count = 0
    for result in results:
        for row in _csv_rows(result.file):
            row_text = " ".join(row.values()).lower()
            if not all(term in row_text for term in match_terms):
                continue
            amount = _money(row.get("Amount", row.get("amount", "")))
            if amount is None:
                continue
            currency, value = amount
            totals[currency] = totals.get(currency, Decimal()) + value
            count += 1
    if not totals:
        return None

    formatted_totals = ", ".join(
        f"{currency}{value:,.2f}" for currency, value in totals.items()
    )
    return f"The total is {formatted_totals} across {count} matching transaction{'s' if count != 1 else ''}."


def answer_drive_question(question: str, directory: Path = DRIVE_DIRECTORY) -> dict:
    """Answer a question using only locally exported Drive files."""
    results = search_drive(question, directory=directory)
    if not results:
        return {
            "answer": "I couldn't find a Drive file that matches that question in the local export.",
            "sources": [],
        }

    top = results[0]
    total_answer = _total_answer(question, results)
    if total_answer:
        source_results = results[:1]
        answer = total_answer
    elif len(results) == 1 or top.score >= results[1].score + 4:
        source_results = results[:1]
        answer = top.excerpt
    else:
        source_results = results[:3]
        answer = "I found {} relevant Drive files. {}".format(
            len(source_results),
            "; ".join(f"{result.file.name}: {result.excerpt}" for result in source_results),
        )

    # Spreadsheet totals are calculated deterministically; do not let a model
    # re-interpret an exact monetary answer. Other Drive questions may use the
    # source-grounded model when ANTHROPIC_API_KEY is configured.
    if not total_answer:
        answer = synthesize_answer(
            question,
            (
                f"Name: {result.file.name}\nOwner: {result.file.owner}\n"
                f"Modified: {result.file.modified_time}\n\n{result.file.body}"
                for result in source_results
            ),
            answer,
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
