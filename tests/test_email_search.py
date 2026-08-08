from pathlib import Path
import unittest

from api.email_search import answer_email_question, search_emails


def _write_email(directory: Path, name: str, subject: str, body: str) -> None:
    (directory / name).write_text(
        f"---\nsource: gmail\ngmail_id: {name}\nsubject: {subject}\nfrom: sender@example.com\n"
        "to: me@example.com\ndate: '2026-08-07T13:59:15+00:00'\ngmail_link: https://example.com\n---\n"
        f"{body}\n",
        encoding="utf-8",
    )


class EmailSearchTests(unittest.TestCase):
    def test_exact_terms_rank_relevant_email_and_answer_with_evidence(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            _write_email(directory, "snorkel.md", "Snorkel Sentinel assessment", "Project pay: Fixable tasks — ₹7,000 per accepted submission.")
            _write_email(directory, "newsletter.md", "Internship news", "A high-paying internship is available.")

            results = search_emails("What is the pay of fixable Snorkel task?", directory=directory)
            response = answer_email_question("What is the pay of fixable Snorkel task?", directory=directory)

        self.assertEqual(results[0].email.subject, "Snorkel Sentinel assessment")
        self.assertIn("₹7,000", response["answer"])
        self.assertEqual(response["sources"][0]["id"], "snorkel.md")
        self.assertEqual(len(response["sources"]), 1)
