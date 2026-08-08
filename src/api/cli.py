"""Command-line entry point for Tier-1 Gmail questions."""

from __future__ import annotations

import argparse

from .email_search import answer_email_question


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search local Gmail and return an evidence-backed answer"
    )
    parser.add_argument("question", help="Natural-language email question")
    args = parser.parse_args()

    response = answer_email_question(args.question)
    print(response["answer"])
    for source in response["sources"]:
        print(f"\nSource: {source['subject']} — {source['from']} ({source['date']})")
        if source["link"]:
            print(source["link"])
