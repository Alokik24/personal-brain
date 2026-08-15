"""Evidence-grounded LLM synthesis for retrieved Personal Brain data."""

from __future__ import annotations

import json
import os
from typing import Any, Iterable
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv()


def synthesize_answer_with_citations(
    question: str,
    evidence: Iterable[dict[str, Any]],
    fallback: str,
) -> dict[str, Any]:
    """Synthesize an answer from multi-source evidence and validate citations.

    Evidence entries must contain ``source_type``, ``title`` and ``text``.
    Citation quotes are checked against the exact supplied source text before
    being returned, so the model cannot invent a citation target.
    """
    items = list(evidence)
    if not items:
        return {"answer": "I don't know from the retrieved records.", "citations": []}

    api_key = os.getenv("OPENROUTER_API_KEY")
    enabled = os.getenv("PERSONAL_BRAIN_ENABLE_SYNTHESIS", "").lower() in {"1", "true", "yes"}
    if not api_key or not enabled:
        return {
            "answer": fallback,
            "citations": [
                {"source": i, "source_type": item["source_type"], "title": item["title"], "quote": item["excerpt"]}
                for i, item in enumerate(items, start=1)
            ],
        }

    source_texts = [str(item["text"])[:6_000] for item in items]
    context = "\n\n".join(
        f"--- SOURCE {index} ({item['source_type']}: {item['title']}) ---\n{text}"
        for index, (item, text) in enumerate(zip(items, source_texts), start=1)
    )
    system = """You answer questions about a user's Gmail and Google Drive data.
Use ONLY the supplied source text. You may combine facts from multiple sources,
but every factual claim must be supported by the supplied evidence. Do not use
outside knowledge or infer missing facts. If the evidence does not answer the
question, answer exactly: I don't know from the retrieved records.

Return ONLY valid JSON:
{"answer":"concise conversational answer", "citations":[{"source":1,"quote":"exact supporting quote"}]}

Every non-refusal answer must contain at least one citation. The source number
must identify one of the supplied sources, and quote must be copied verbatim
from that source. Prefer citations from both Gmail and Drive when both are
material to the answer."""
    try:
        request = Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps({
                "model": os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.6"),
                "max_tokens": 500,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Question: {question}\n\nSources:\n{context}"},
                ],
            }).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-OpenRouter-Title": "Personal Brain",
            },
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            payload = json.loads(json.loads(response.read().decode("utf-8"))["choices"][0]["message"]["content"])
    except Exception:
        return {"answer": fallback, "citations": []}

    answer = payload.get("answer", "").strip() if isinstance(payload, dict) else ""
    citations = payload.get("citations", []) if isinstance(payload, dict) else []
    if not answer or answer == "I don't know from the retrieved records.":
        return {"answer": "I don't know from the retrieved records.", "citations": []}
    if not isinstance(citations, list) or not citations:
        return {"answer": fallback, "citations": []}

    validated: list[dict[str, Any]] = []
    for citation in citations:
        if not isinstance(citation, dict):
            return {"answer": fallback, "citations": []}
        source_index = citation.get("source")
        quote = citation.get("quote", "")
        if not isinstance(source_index, int) or not 1 <= source_index <= len(source_texts):
            return {"answer": fallback, "citations": []}
        if not isinstance(quote, str) or not quote.strip() or quote not in source_texts[source_index - 1]:
            return {"answer": fallback, "citations": []}
        item = items[source_index - 1]
        validated.append({
            "source": source_index,
            "source_type": item["source_type"],
            "title": item["title"],
            "quote": quote,
        })

    return {"answer": answer, "citations": validated}


def synthesize_answer(
    question: str,
    evidence: Iterable[str],
    fallback: str,
    source_name: str,
) -> str:
    """Backward-compatible single-source synthesis used by existing modules."""
    items = [
        {"source_type": source_name.lower(), "title": source_name, "text": text, "excerpt": text[:500]}
        for text in evidence
    ]
    return synthesize_answer_with_citations(question, items, fallback)["answer"]
