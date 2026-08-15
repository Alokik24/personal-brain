"""Optional LLM synthesis that is constrained to retrieved local evidence."""

from __future__ import annotations

import os
import json
from typing import Iterable
from urllib.request import Request, urlopen

from dotenv import load_dotenv


INSUFFICIENT_EVIDENCE = "I don't know from the retrieved {source} records."
load_dotenv()


def synthesize_answer(
    question: str,
    evidence: Iterable[str],
    fallback: str,
    source_name: str,
) -> str:
    """Create a conversational answer only when an API key is explicitly available.

    On missing configuration, API errors, refusals, or an evidence refusal from
    the model, deterministic retrieval remains the answer path.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    enabled = os.getenv("PERSONAL_BRAIN_ENABLE_SYNTHESIS", "").lower() in {"1", "true", "yes"}
    if not api_key or not enabled:
        return fallback

    source_texts = [item[:6_000] for item in evidence]
    if not source_texts:
        return INSUFFICIENT_EVIDENCE.format(source=source_name)
    context = "\n\n".join(
        f"--- SOURCE {index} ---\n{text}" for index, text in enumerate(source_texts, start=1)
    )
    system = f"""You answer questions about a user's {source_name} data.
Use ONLY the supplied source text. Do not use outside knowledge, infer missing
facts, or claim that a source says something it does not. If the answer is not
directly supported, set the answer to exactly: {INSUFFICIENT_EVIDENCE.format(source=source_name)}
Return ONLY valid JSON in this shape:
{{"answer":"concise answer", "evidence":[{{"source":1,"quote":"an exact supporting quote"}}]}}
For every non-refusal answer, provide at least one exact quote copied from a
source. Do not use Markdown or add any text outside the JSON."""
    try:
        request = Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(
                {
                    "model": os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.6"),
                    "max_tokens": 300,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": f"Question: {question}\n\nSources:\n{context}"},
                    ],
                }
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-OpenRouter-Title": "Personal Brain",
            },
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            provider_response = json.loads(response.read().decode("utf-8"))
        raw_answer = provider_response["choices"][0]["message"]["content"].strip()
        payload = json.loads(raw_answer)
        answer = payload.get("answer", "").strip()
        citations = payload.get("evidence", [])
    except Exception:
        return fallback
    if not answer or answer == INSUFFICIENT_EVIDENCE.format(source=source_name):
        return INSUFFICIENT_EVIDENCE.format(source=source_name)
    if not isinstance(citations, list) or not citations:
        return fallback
    for citation in citations:
        if not isinstance(citation, dict):
            return fallback
        source_index = citation.get("source")
        quote = citation.get("quote", "")
        if not isinstance(source_index, int) or not isinstance(quote, str) or not quote.strip():
            return fallback
        if source_index < 1 or source_index > len(source_texts) or quote not in source_texts[source_index - 1]:
            return fallback
    return answer
