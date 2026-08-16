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

# Fallback models are only used if the configured/default GBrain model
# cannot produce an answer. This keeps the demo resilient to provider
# credit/rate-limit failures without changing retrieval behavior.
FALLBACK_MODELS = [
    "openrouter:google/gemini-2.5-flash-lite",
    "openrouter:google/gemini-2.5-flash",
]

# GBrain think citations look like:
# [19fdc9cd02c41a52]
# [1UHdJoKdpQkJ6Ej0KoRdzIBvCJlNRuPpbQmcc_b3GgLg]
CITATION_RE = re.compile(r"\[([A-Za-z0-9_-]+)\]")


def _normalize_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _clean_answer(output: str) -> str:
    """Remove GBrain CLI metadata while preserving the actual answer."""

    text = output.strip()

    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]

    text = "\n".join(lines).strip()

    gaps_marker = "\n## Gaps"
    if gaps_marker in text:
        text = text.split(gaps_marker, 1)[0].rstrip()

    footer_markers = ("\n---\nModel:", "\nModel:")
    for marker in footer_markers:
        if marker in text:
            text = text.split(marker, 1)[0].rstrip()

    return text


def _looks_like_model_failure(output: str) -> bool:
    """Detect GBrain output indicating that synthesis could not run."""

    failure_markers = (
        "no LLM available",
        "requires more credits",
        "fewer max_tokens",
        "provider API",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "model not found",
        "rate limit",
        "rate_limit",
    )

    lowered = output.lower()
    return any(marker.lower() in lowered for marker in failure_markers)


def _run_gbrain(
    question: str,
    model: str | None = None,
) -> tuple[str, str]:
    """Run gbrain think and return (stdout, stderr)."""

    prompt = f"""
Answer the user's question using evidence from the connected personal brain.

Grounding rules:
- Use only facts supported by retrieved evidence.
- For cross-source questions, explicitly establish the relationship between
  the sources before combining their facts.
- Do not treat two documents as related merely because they contain similar
  words such as "assessment", "application", "take-home", or "job".
- If the question asks for a corresponding, related, attached, submitted, or
  associated document, require evidence that actually connects that document
  to the relevant email, person, company, or event.
- Do not substitute an unrelated document that merely matches the topic.
- If the requested relationship cannot be established from the evidence,
  say that it cannot be determined rather than guessing.

User question:
{question}
"""

    command = [GBRAIN_COMMAND, "think", prompt]

    if model:
        command.extend(["--model", model])

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )

    return completed.stdout.strip(), completed.stderr.strip()


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


def _build_response(
    raw_output: str,
    email_directory: Path,
    drive_directory: Path,
) -> dict[str, Any]:
    """Convert GBrain output into the response shape expected by Streamlit."""

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


def answer_gbrain_question(
    question: str,
    *,
    email_directory: Path = EMAIL_DIRECTORY,
    drive_directory: Path = DRIVE_DIRECTORY,
) -> dict[str, Any]:
    """Ask GBrain to retrieve and reason over the connected brain.

    GBrain's configured model is tried first. If synthesis fails because
    the model/provider is unavailable, configured fallback models are tried
    in order.
    """

    try:
        raw_output, error = _run_gbrain(question)

        if (
            raw_output
            and not _looks_like_model_failure(raw_output)
        ):
            return _build_response(
                raw_output,
                email_directory,
                drive_directory,
            )

        # The default/configured model failed to produce an answer.
        # Try the demo-safe fallback models.
        last_error = error or raw_output

        for model in FALLBACK_MODELS:
            try:
                fallback_output, fallback_error = _run_gbrain(
                    question,
                    model=model,
                )

                if (
                    fallback_output
                    and not _looks_like_model_failure(fallback_output)
                ):
                    return _build_response(
                        fallback_output,
                        email_directory,
                        drive_directory,
                    )

                last_error = fallback_error or fallback_output or last_error

            except (OSError, subprocess.SubprocessError) as exc:
                last_error = str(exc)

        return {
            "answer": (
                "I couldn't answer that from the connected brain."
                if not last_error
                else f"GBrain could not answer the question: {last_error}"
            ),
            "sources": [],
            "citations": [],
        }

    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "answer": f"GBrain could not be reached: {exc}",
            "sources": [],
            "citations": [],
        }