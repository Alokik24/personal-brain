"""Command-line entry point for questions over local Google Drive exports."""

from __future__ import annotations

import argparse

from .drive_search import answer_drive_question


def main() -> None:
    parser = argparse.ArgumentParser(description="Search local Google Drive files")
    parser.add_argument("question", help="Natural-language Drive question")
    args = parser.parse_args()
    response = answer_drive_question(args.question)
    print(response["answer"])
    for source in response["sources"]:
        print(f"\nSource: {source['name']} — {source['owner']} ({source['modified_time']})")
        if source["link"]:
            print(source["link"])
