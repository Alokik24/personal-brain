from pathlib import Path
import unittest

from api.drive_search import answer_drive_question, search_drive


def _write_drive_file(directory: Path, file_id: str, name: str, content: str) -> None:
    (directory / f"{file_id}.md").write_text(
        "---\n"
        f"name: {name}\n"
        "mime_type: application/vnd.google-apps.document\n"
        "modified_time: '2026-08-08T12:00:00Z'\n"
        "drive_link: https://drive.google.com/example\n"
        "owner: owner@example.com\n"
        "---\n"
        f"{content}\n",
        encoding="utf-8",
    )


class DriveSearchTests(unittest.TestCase):
    def test_title_and_content_terms_rank_the_matching_drive_file(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            _write_drive_file(
                directory,
                "takehome",
                "Snorkel take-home submission",
                "# Snorkel take-home submission\n\n- MIME type: document\n\n"
                "Build a Personal Brain, a conversational agent over connected personal data.",
            )
            _write_drive_file(directory, "notes", "Interview notes", "A generic meeting summary.")

            results = search_drive("Where is my Snorkel take-home submission?", directory=directory)
            response = answer_drive_question("Where is my Snorkel take-home submission?", directory=directory)

        self.assertEqual(results[0].file.id, "takehome")
        self.assertIn("Build a Personal Brain", response["answer"])
        self.assertEqual(response["sources"][0]["name"], "Snorkel take-home submission")

    def test_total_question_sums_all_matching_sheet_rows(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            _write_drive_file(
                directory,
                "expenses",
                "Expenses",
                "Transaction ID,Date,Description,Category,Type,Amount,Status\n"
                'TXN-1,2026-01-01,Salary Deposit,Income,Income,"$5,000.00",Completed\n'
                'TXN-2,2026-01-20,Salary Deposit,Income,Income,"$5,000.00",Completed\n'
                'TXN-3,2026-01-21,Coffee,Food,Expense,"$5.00",Completed',
            )
            response = answer_drive_question("What is my salary deposit total?", directory=directory)

        self.assertEqual(response["answer"], "The total is $10,000.00 across 2 matching transactions.")
