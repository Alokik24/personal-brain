"""Thin adapter around the local GBrain CLI.

GBrain is used for semantic candidate discovery only. The application hydrates
returned IDs from the authoritative Gmail/Drive local exports.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess


GBRAIN_COMMAND = "gbrain"
RESULT_RE = re.compile(
    r"^\[(?P<score>-?\d+(?:\.\d+)?)\]\s+"
    r"(?P<id>\S+)\s+--\s+(?P<title>.*)$"
)


@dataclass(frozen=True)
class GBrainResult:
    id: str
    score: float
    title: str


def search_gbrain(
    question: str,
    *,
    limit: int = 10,
    command: str = GBRAIN_COMMAND,
) -> list[GBrainResult]:
    """Return semantic candidates from GBrain.

    A GBrain failure is deliberately treated as an empty candidate set.
    Source-specific retrieval remains available as the fallback path.
    """
    try:
        completed = subprocess.run(
            [command, "search", question],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    if completed.returncode != 0:
        return []

    results: list[GBrainResult] = []

    for line in completed.stdout.splitlines():
        match = RESULT_RE.match(line.strip())
        if not match:
            continue

        results.append(
            GBrainResult(
                id=match.group("id"),
                score=float(match.group("score")),
                title=match.group("title").strip(),
            )
        )

        if len(results) >= limit:
            break

    return results