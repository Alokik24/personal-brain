"""Unified cross-source retrieval for Gmail + Google Drive.

GBrain provides semantic candidate discovery. Gmail and Drive local exports
remain the authoritative source of record.

The unified layer:
1. retrieves candidates independently from Gmail, Drive, and GBrain;
2. hydrates GBrain candidates from the authoritative local corpora;
3. detects generic cross-source relationships;
4. returns correlated evidence when a relationship exists;
5. avoids mixing unrelated Gmail and Drive records when no relationship
   can be established.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .drive_search import (
    DRIVE_DIRECTORY,
    DriveFile,
    DriveSearchResult,
    load_drive_files,
    search_drive,
)
from .email_search import (
    EMAIL_DIRECTORY,
    Email,
    SearchResult,
    load_emails,
    search_emails,
)
from .gbrain_search import GBrainResult, search_gbrain
from .grounded_synthesis import synthesize_answer_with_citations


DEFAULT_LIMIT_PER_SOURCE = 5
GBRAIN_DISCOVERY_LIMIT = 10


@dataclass(frozen=True)
class Correlation:
    gmail_id: str
    drive_id: str
    score: float
    signals: tuple[str, ...]


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) >= 3
    }


# ---------------------------------------------------------------------------
# Evidence conversion
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Cross-source correlation
# ---------------------------------------------------------------------------


def _all_text(email: Email) -> str:
    return " ".join(
        (
            email.subject,
            email.sender,
            email.recipient,
            email.body,
        )
    )


def _drive_text(file: DriveFile) -> str:
    return " ".join(
        (
            file.name,
            file.owner,
            file.mime_type,
            file.body,
        )
    )


def _correlate_pair(
    email: Email,
    drive: DriveFile,
) -> Correlation | None:
    """Find a defensible relationship between one Gmail and Drive record.

    Relationships are generic. Nothing in this function depends on a
    particular company, person, filename, or assignment.

    Strong anchors can establish a relationship:
      - exact Drive URL
      - exact Drive identifier
      - distinctive artifact-name overlap

    Shared vocabulary and temporal proximity can only support an already
    established relationship.
    """

    email_text = _normalize_text(_all_text(email))
    drive_text = _normalize_text(_drive_text(drive))

    email_tokens = _tokens(email_text)
    drive_tokens = _tokens(drive_text)

    strong_signals: list[str] = []
    supporting_signals: list[str] = []
    score = 0.0

    # ------------------------------------------------------------------
    # 1. Exact Drive URL mentioned in Gmail.
    # ------------------------------------------------------------------

    if drive.link:
        normalized_link = _normalize_text(drive.link)

        if normalized_link and normalized_link in email_text:
            strong_signals.append("Drive URL mentioned in Gmail")
            score += 20

    # ------------------------------------------------------------------
    # 2. Exact Drive ID mentioned in Gmail.
    # ------------------------------------------------------------------

    normalized_drive_id = _normalize_identifier(drive.id)
    normalized_email = _normalize_identifier(email_text)

    if (
        normalized_drive_id
        and len(normalized_drive_id) >= 8
        and normalized_drive_id in normalized_email
    ):
        strong_signals.append("Drive identifier mentioned in Gmail")
        score += 20

    # ------------------------------------------------------------------
    # 3. Distinctive artifact-name relationship.
    #
    # Generic words are ignored. A relationship requires multiple
    # distinctive filename tokens.
    # ------------------------------------------------------------------

    generic_filename_terms = {
        "document",
        "file",
        "pdf",
        "doc",
        "sheet",
        "google",
        "drive",
        "shared",
        "copy",
        "final",
        "draft",
        "version",
        "untitled",
    }

    personal_name_terms = {
        "alokik",
        "garg",
    }

    name_tokens = (
        _tokens(drive.name)
        - generic_filename_terms
        - personal_name_terms
    )

    if len(name_tokens) >= 2:
        overlap = name_tokens & email_tokens

        if (
            len(overlap) >= 2
            and len(overlap) / len(name_tokens) >= 0.75
        ):
            strong_signals.append(
                "distinctive artifact name overlap"
            )
            score += 12

        elif len(overlap) >= 2:
            supporting_signals.append(
                "partial artifact name overlap"
            )

    # ------------------------------------------------------------------
    # 4. Shared distinctive terminology.
    #
    # This NEVER creates a relationship by itself.
    # ------------------------------------------------------------------

    generic_terms = generic_filename_terms | {
        "application",
        "applications",
        "applied",
        "apply",
        "candidate",
        "candidates",
        "job",
        "jobs",
        "role",
        "position",
        "engineer",
        "engineering",
        "email",
        "mail",
        "please",
        "thank",
        "thanks",
        "interest",
        "opportunity",
        "opportunities",
        "review",
        "regards",
        "hello",
        "hi",
        "dear",
        "alokik",
        "garg",
    }

    meaningful_overlap = {
        token
        for token in email_tokens & drive_tokens
        if token not in generic_terms
    }

    if len(meaningful_overlap) >= 4:
        supporting_signals.append(
            "multiple shared distinctive terms"
        )
        score += 3

    elif len(meaningful_overlap) >= 3:
        supporting_signals.append(
            "shared project terminology"
        )
        score += 1.5

    # ------------------------------------------------------------------
    # 5. Temporal proximity.
    #
    # Supporting evidence only.
    # ------------------------------------------------------------------

    same_day = False

    if email.date and drive.modified_time:
        email_date = email.date[:10]
        drive_date = drive.modified_time[:10]

        if email_date and drive_date and email_date == drive_date:
            same_day = True
            supporting_signals.append("same calendar date")

    # ------------------------------------------------------------------
    # 6. Relationship decision.
    #
    # Generic semantic overlap and temporal proximity cannot create an
    # edge. At least one strong anchor is required.
    # ------------------------------------------------------------------

    if not strong_signals:
        return None

    if same_day:
        score += 0.5

    return Correlation(
        gmail_id=email.id,
        drive_id=drive.id,
        score=score,
        signals=tuple(
            strong_signals + supporting_signals
        ),
    )


def _build_correlations(
    emails: list[Email],
    drives: list[DriveFile],
) -> list[Correlation]:
    correlations: list[Correlation] = []

    for email in emails:
        for drive in drives:
            correlation = _correlate_pair(email, drive)

            if correlation:
                correlations.append(correlation)

    return sorted(
        correlations,
        key=lambda item: item.score,
        reverse=True,
    )


# ---------------------------------------------------------------------------
# GBrain hydration
# ---------------------------------------------------------------------------


def _gbrain_hydrated_candidates(
    gbrain_results: list[GBrainResult],
    emails: list[Email],
    drives: list[DriveFile],
) -> tuple[list[Email], list[DriveFile]]:
    """Map GBrain result IDs back to authoritative local records."""

    email_by_id = {
        _normalize_identifier(email.id): email
        for email in emails
    }

    drive_by_id = {
        _normalize_identifier(drive.id): drive
        for drive in drives
    }

    selected_emails: list[Email] = []
    selected_drives: list[DriveFile] = []

    seen_emails: set[str] = set()
    seen_drives: set[str] = set()

    for result in gbrain_results:
        normalized_id = _normalize_identifier(result.id)

        email = email_by_id.get(normalized_id)

        if email and normalized_id not in seen_emails:
            selected_emails.append(email)
            seen_emails.add(normalized_id)
            continue

        drive = drive_by_id.get(normalized_id)

        if drive and normalized_id not in seen_drives:
            selected_drives.append(drive)
            seen_drives.add(normalized_id)

    return selected_emails, selected_drives


# ---------------------------------------------------------------------------
# Hydration helpers
# ---------------------------------------------------------------------------


def _search_result_for_email(
    email: Email,
    results: list[SearchResult],
) -> SearchResult:
    for result in results:
        if result.email.id == email.id:
            return result

    return SearchResult(
        email=email,
        score=0.0,
        excerpt=email.body[:500],
    )


def _search_result_for_drive(
    drive: DriveFile,
    results: list[DriveSearchResult],
) -> DriveSearchResult:
    for result in results:
        if result.file.id == drive.id:
            return result

    return DriveSearchResult(
        file=drive,
        score=0.0,
        excerpt=drive.body[:500],
    )


# ---------------------------------------------------------------------------
# Unified retrieval
# ---------------------------------------------------------------------------


def search_all_sources(
    question: str,
    *,
    limit_per_source: int = DEFAULT_LIMIT_PER_SOURCE,
    email_directory: Path = EMAIL_DIRECTORY,
    drive_directory: Path = DRIVE_DIRECTORY,
) -> list[dict[str, Any]]:
    """Retrieve evidence across Gmail and Drive.

    The important distinction is:

        candidate != evidence

    Gmail, Drive and GBrain can all produce candidates.

    A candidate becomes final cross-source evidence only when:
      1. it participates in a defensible cross-source relationship, or
      2. it is the only source containing relevant candidates.

    If both sources contain candidates but no relationship can be
    established, the unified layer refuses to combine them.
    """

    # ------------------------------------------------------------------
    # 1. Preserve existing source-specific retrieval.
    # ------------------------------------------------------------------

    email_results = search_emails(
        question,
        limit=limit_per_source,
        directory=email_directory,
    )

    drive_results = search_drive(
        question,
        limit=limit_per_source,
        directory=drive_directory,
    )

    # ------------------------------------------------------------------
    # 2. GBrain semantic discovery.
    # ------------------------------------------------------------------

    gbrain_results = search_gbrain(
        question,
        limit=GBRAIN_DISCOVERY_LIMIT,
    )

    # ------------------------------------------------------------------
    # 3. Hydrate GBrain IDs against authoritative local data.
    # ------------------------------------------------------------------

    all_emails = load_emails(email_directory)
    all_drives = load_drive_files(drive_directory)

    gbrain_emails, gbrain_drives = _gbrain_hydrated_candidates(
        gbrain_results,
        all_emails,
        all_drives,
    )

    # ------------------------------------------------------------------
    # 4. Merge source-specific and GBrain candidates.
    # ------------------------------------------------------------------

    email_candidates: dict[str, Email] = {
        result.email.id: result.email
        for result in email_results
    }

    drive_candidates: dict[str, DriveFile] = {
        result.file.id: result.file
        for result in drive_results
    }

    for email in gbrain_emails:
        email_candidates[email.id] = email

    for drive in gbrain_drives:
        drive_candidates[drive.id] = drive

    candidate_emails = list(email_candidates.values())
    candidate_drives = list(drive_candidates.values())

    # ------------------------------------------------------------------
    # 5. Build the generic cross-source relationship graph.
    # ------------------------------------------------------------------

    correlations = _build_correlations(
        candidate_emails,
        candidate_drives,
    )

    # ------------------------------------------------------------------
    # 6. If relationships exist, ONLY correlated records become
    #    cross-source evidence.
    # ------------------------------------------------------------------

    if correlations:
        email_lookup = {
            email.id: email
            for email in candidate_emails
        }

        drive_lookup = {
            drive.id: drive
            for drive in candidate_drives
        }

        email_result_lookup = {
            result.email.id: result
            for result in email_results
        }

        drive_result_lookup = {
            result.file.id: result
            for result in drive_results
        }

        evidence: list[dict[str, Any]] = []

        correlation_score_by_id: dict[tuple[str, str], float] = {}

        for correlation in correlations:
            correlation_score_by_id[
                ("gmail", correlation.gmail_id)
            ] = max(
                correlation_score_by_id.get(
                    ("gmail", correlation.gmail_id),
                    0.0,
                ),
                correlation.score,
            )

            correlation_score_by_id[
                ("drive", correlation.drive_id)
            ] = max(
                correlation_score_by_id.get(
                    ("drive", correlation.drive_id),
                    0.0,
                ),
                correlation.score,
            )

        correlated_email_ids = {
            correlation.gmail_id
            for correlation in correlations
        }

        correlated_drive_ids = {
            correlation.drive_id
            for correlation in correlations
        }

        for email_id in correlated_email_ids:
            email = email_lookup[email_id]

            result = email_result_lookup.get(email_id)

            if result is None:
                result = _search_result_for_email(
                    email,
                    email_results,
                )

            evidence.append(
                _email_evidence(result)
            )

        for drive_id in correlated_drive_ids:
            drive = drive_lookup[drive_id]

            result = drive_result_lookup.get(drive_id)

            if result is None:
                result = _search_result_for_drive(
                    drive,
                    drive_results,
                )

            evidence.append(
                _drive_evidence(result)
            )

        evidence.sort(
            key=lambda item: (
                correlation_score_by_id.get(
                    (
                        item["source_type"],
                        item["source_id"],
                    ),
                    0.0,
                ),
                item["score"],
            ),
            reverse=True,
        )

        return evidence

    # ------------------------------------------------------------------
    # 7. No cross-source relationship.
    #
    # Do NOT concatenate Gmail + Drive results. That was the original
    # failure mode.
    #
    # If only one source has candidates, it is safe to treat those as
    # single-source evidence.
    #
    # If both sources have candidates but cannot be related, return no
    # unified evidence rather than presenting unrelated records together.
    # ------------------------------------------------------------------

    has_email_candidates = bool(email_results or gbrain_emails)
    has_drive_candidates = bool(drive_results or gbrain_drives)

    if has_email_candidates and not has_drive_candidates:
        return [
            _email_evidence(result)
            for result in email_results
        ]

    if has_drive_candidates and not has_email_candidates:
        return [
            _drive_evidence(result)
            for result in drive_results
        ]

    # Both sources produced candidates, but no defensible relationship
    # exists between them. Refuse to manufacture cross-source evidence.
    return []


# ---------------------------------------------------------------------------
# Answer generation
# ---------------------------------------------------------------------------


def answer_question(
    question: str,
    *,
    limit_per_source: int = DEFAULT_LIMIT_PER_SOURCE,
    email_directory: Path = EMAIL_DIRECTORY,
    drive_directory: Path = DRIVE_DIRECTORY,
) -> dict[str, Any]:
    """Answer a question using grounded unified evidence."""

    evidence = search_all_sources(
        question,
        limit_per_source=limit_per_source,
        email_directory=email_directory,
        drive_directory=drive_directory,
    )

    if not evidence:
        return {
            "answer": (
                "I couldn't establish enough relevant evidence "
                "across the connected Gmail and Google Drive data "
                "to answer that reliably."
            ),
            "sources": [],
            "citations": [],
        }

    # At this point evidence has already passed the relevance /
    # correlation gate. This limit only controls context size.
    context = evidence[: limit_per_source * 2]

    fallback_parts = [
        f"[{item['source_type']}] "
        f"{item['title']}: "
        f"{item['excerpt']}"
        for item in context[:3]
    ]

    fallback = (
        "I found relevant evidence. "
        + " ".join(fallback_parts)
    )

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