"""GBrain-backed cross-source question answering.

GBrain owns retrieval and cross-source reasoning for the "Both" path.
The local Gmail/Drive exports are used only to hydrate cited source metadata
for the UI.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from .drive_search import DRIVE_DIRECTORY, load_drive_files
from .email_search import EMAIL_DIRECTORY, load_emails


GBRAIN_COMMAND = "gbrain"

# GBrain think citations look like:
# [19fdc9cd02c41a52]
# [1UHdJoKdpQkJ6Ej0KoRdzIBvCJlNRuPpbQmcc_b3GgLg]
CITATION_RE = re.compile(r"\[([A-Za-z0-9_-]+)\]")


def _normalize_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _clean_answer(output: str) -> str:
    """Remove GBrain CLI metadata while preserving the actual answer."""

    text = output.strip()

    # Remove the "# question" heading.
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]

    text = "\n".join(lines).strip()

    # GBrain puts uncertainty/gaps after the actual answer.
    gaps_marker = "\n## Gaps"
    if gaps_marker in text:
        text = text.split(gaps_marker, 1)[0].rstrip()

    # Remove the CLI metadata footer.
    footer_markers = ("\n---\nModel:", "\nModel:")
    for marker in footer_markers:
        if marker in text:
            text = text.split(marker, 1)[0].rstrip()

    return text


def _build_source_index(
    email_directory: Path,
    drive_directory: Path,
) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}

    for email in load_emails(email_directory):
        sources[_normalize_id(email.id)] = {
            "source_type": "gmail",
            "id": email.id,
            "title": email.subject,
            "link": email.link,
            "quote": email.body[:500],
        }

    for drive in load_drive_files(drive_directory):
        sources[_normalize_id(drive.id)] = {
            "source_type": "drive",
            "id": drive.id,
            "title": drive.name,
            "link": drive.link,
            "quote": drive.body[:500],
        }

    return sources


def answer_gbrain_question(
    question: str,
    *,
    email_directory: Path = EMAIL_DIRECTORY,
    drive_directory: Path = DRIVE_DIRECTORY,
) -> dict[str, Any]:
    """Ask GBrain to retrieve and reason over the connected brain."""

    try:
        completed = subprocess.run(
            [GBRAIN_COMMAND, "think", question],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "answer": f"GBrain could not be reached: {exc}",
            "sources": [],
            "citations": [],
        }

    if completed.returncode != 0:
        error = completed.stderr.strip() or completed.stdout.strip()

        return {
            "answer": (
                "I couldn't answer that from the connected brain."
                if not error
                else f"GBrain could not answer the question: {error}"
            ),
            "sources": [],
            "citations": [],
        }

    raw_output = completed.stdout.strip()

    if not raw_output:
        return {
            "answer": "I couldn't find enough information in the connected brain.",
            "sources": [],
            "citations": [],
        }

    answer = _clean_answer(raw_output)

    if not answer:
        answer = "I couldn't find enough information in the connected brain."

    source_index = _build_source_index(
        email_directory,
        drive_directory,
    )

    citations: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw_id in CITATION_RE.findall(raw_output):
        normalized = _normalize_id(raw_id)

        if normalized in seen:
            continue

        source = source_index.get(normalized)

        if source is None:
            continue

        seen.add(normalized)

        citations.append(
            {
                "source": source["id"],
                "source_type": source["source_type"],
                "title": source["title"],
                "quote": source["quote"],
            }
        )

    sources = [
        {
            "source_type": citation["source_type"],
            "id": citation["source"],
            "title": citation["title"],
            "link": source_index[
                _normalize_id(citation["source"])
            ]["link"],
        }
        for citation in citations
    ]

    return {
        "answer": answer,
        "sources": sources,
        "citations": citations,
    }