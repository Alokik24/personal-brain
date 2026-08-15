#!/usr/bin/env python3
"""Ingest Google Drive file metadata into local markdown pages and gbrain.

OAuth credentials may be supplied as DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET, and
DRIVE_REFRESH_TOKEN.  The Gmail-named variants are accepted as a convenience
when both APIs use the same Google OAuth client.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from typing import Any

from dotenv import load_dotenv
import frontmatter
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DRIVE_OUTPUT_DIR = PROJECT_ROOT / "brain-source" / "drives"
PDF_OUTPUT_DIR = DRIVE_OUTPUT_DIR / "raw"
INGESTED_IDS_FILE = PROJECT_ROOT / "ingested_drive_ids.json"
FILE_FIELDS = (
    "nextPageToken,files(id,name,mimeType,description,createdTime,modifiedTime,"
    "webViewLink,parents,owners(displayName,emailAddress),shared,trashed,size,"
    "md5Checksum)"
)
GOOGLE_EXPORT_MIME_TYPES = {
    "application/vnd.google-apps.document": "text/plain",
    # Google Sheets does not support text/plain export; CSV is its plain-text
    # representation and preserves the cell contents for this MVP.
    "application/vnd.google-apps.spreadsheet": "text/csv",
}


def _credential_value(drive_name: str, gmail_name: str) -> str | None:
    """Get a Drive-specific credential, falling back to the Gmail OAuth client."""
    return os.getenv(drive_name) or os.getenv(gmail_name)


def get_credentials() -> Credentials:
    client_id = _credential_value("DRIVE_CLIENT_ID", "GMAIL_CLIENT_ID")
    client_secret = _credential_value("DRIVE_CLIENT_SECRET", "GMAIL_CLIENT_SECRET")
    refresh_token = _credential_value("DRIVE_REFRESH_TOKEN", "GMAIL_REFRESH_TOKEN")
    if not all((client_id, client_secret, refresh_token)):
        raise ValueError(
            "Missing Drive OAuth credentials. Set DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET, "
            "and DRIVE_REFRESH_TOKEN (or the matching GMAIL_* variables)."
        )

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    try:
        credentials.refresh(Request())
    except RefreshError as error:
        raise RuntimeError(
            "Could not refresh the Drive token. Re-authorize it with the "
            "drive.readonly scope."
        ) from error
    return credentials


def get_ingested_ids() -> set[str]:
    if not INGESTED_IDS_FILE.exists():
        return set()
    try:
        return set(json.loads(INGESTED_IDS_FILE.read_text(encoding="utf-8")).get("ids", []))
    except (OSError, ValueError, TypeError) as error:
        print(f"Warning: could not read {INGESTED_IDS_FILE.name}: {error}")
        return set()


def save_ingested_ids(ids: set[str]) -> None:
    INGESTED_IDS_FILE.write_text(
        json.dumps({"ids": sorted(ids), "last_updated": datetime.now().isoformat()}, indent=2),
        encoding="utf-8",
    )


def validate_rfc3339(timestamp: str) -> str:
    """Validate a --modified-after value and return an RFC 3339 UTC value."""
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "Use an ISO 8601 timestamp, for example 2026-08-01T00:00:00Z"
        ) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_query(folder_id: str | None, modified_after: str | None, query: str | None) -> str:
    """Build a Drive API search query without hiding trashed files by accident."""
    clauses = ["trashed = false"]
    if folder_id:
        clauses.append(f"'{folder_id.replace("'", "\\'")}' in parents")
    if modified_after:
        clauses.append(f"modifiedTime > '{modified_after}'")
    if query:
        clauses.append(f"({query})")
    return " and ".join(clauses)


def list_files(service: Any, query: str, max_results: int) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    page_token: str | None = None
    while len(files) < max_results:
        response = service.files().list(
            q=query,
            pageSize=min(100, max_results - len(files)),
            pageToken=page_token,
            fields=FILE_FIELDS,
            orderBy="modifiedTime desc",
            spaces="drive",
        ).execute()
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return files


def _owner(file: dict[str, Any]) -> str:
    owners = file.get("owners", [])
    if not owners:
        return "unknown"
    return owners[0].get("emailAddress") or owners[0].get("displayName") or "unknown"


def download_content(service: Any, file: dict[str, Any]) -> tuple[str, bool]:
    """Return exportable text and whether the file is metadata-only.

    PDFs are downloaded to ``brain-source/drives/raw`` but deliberately are not
    OCR'd or text-extracted in this MVP.
    """
    file_id = file["id"]
    export_mime_type = GOOGLE_EXPORT_MIME_TYPES.get(file.get("mimeType"))
    if export_mime_type:
        try:
            data = service.files().export(fileId=file_id, mimeType=export_mime_type).execute()
            if isinstance(data, bytes):
                return data.decode("utf-8", errors="replace"), False
            return str(data), False
        except HttpError as error:
            return f"Content export failed: {error}", True

    if file.get("mimeType") == "application/pdf":
        try:
            PDF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            data = service.files().get_media(fileId=file_id).execute()
            (PDF_OUTPUT_DIR / f"{file_id}.pdf").write_bytes(data)
            return "PDF downloaded to raw storage; content was not OCR'd.", True
        except HttpError as error:
            return f"PDF download failed; content was not OCR'd: {error}", True

    return "Metadata only; this file type is not exported in the MVP.", True


def file_to_markdown(file: dict[str, Any], content: str, metadata_only: bool) -> frontmatter.Post:
    owners = file.get("owners", [])
    participants = [owner.get("emailAddress") or owner.get("displayName") for owner in owners]
    participants = [participant for participant in participants if participant]
    name = file.get("name", "[Untitled Drive file]")
    mime_type = file.get("mimeType", "unknown")
    modified = file.get("modifiedTime", "")
    description = file.get("description", "").strip()
    summary = description or f"Google Drive file: {name} ({mime_type})."
    body = "\n".join(
        (
            f"# {name}",
            "",
            f"- MIME type: {mime_type}",
            f"- Modified: {modified or 'unknown'}",
            f"- Owners: {', '.join(participants) or 'unknown'}",
            f"- Shared: {'yes' if file.get('shared') else 'no'}",
            f"- Size: {file.get('size', 'unknown')} bytes",
            f"- Drive link: {file.get('webViewLink', '') or 'unavailable'}",
            "",
            content,
        )
    )
    return frontmatter.Post(
        body,
        name=name,
        mime_type=mime_type,
        modified_time=modified,
        drive_link=file.get("webViewLink", ""),
        owner=_owner(file),
        content_ocrd=not metadata_only,
        content_note=("content was not OCR'd; metadata only" if metadata_only else "exported as plain text"),
    )


def save_file_as_markdown(
    service: Any, file: dict[str, Any], output_dir: Path = DRIVE_OUTPUT_DIR
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{file['id']}.md"
    content, metadata_only = download_content(service, file)
    path.write_text(frontmatter.dumps(file_to_markdown(file, content, metadata_only)), encoding="utf-8")
    return path


def run_gbrain_import() -> bool:
    try:
        result = subprocess.run(
            ["gbrain", "import", "./brain-source/drives/", "--include-gitignored"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=PROJECT_ROOT,
        )
    except FileNotFoundError:
        print("Warning: gbrain command not found; Drive files were saved but not imported.")
        return False
    except subprocess.TimeoutExpired:
        print("Warning: gbrain import timed out.")
        return False

    if result.returncode == 0:
        print("gbrain import completed successfully.")
        return True
    print("gbrain import returned warnings:")
    print(result.stderr or result.stdout)
    return False


def ingest_files(max_results: int, query: str, save_markdown: bool = True) -> int:
    ingested_ids = get_ingested_ids()
    print(f"Previously ingested: {len(ingested_ids)} Drive files")
    service = build("drive", "v3", credentials=get_credentials())
    try:
        files = list_files(service, query, max_results)
    except HttpError as error:
        raise RuntimeError(f"Drive list request failed: {error}") from error

    print(f"Found {len(files)} files matching: {query}")
    saved = 0
    skipped = 0
    for file in files:
        file_id = file["id"]
        if file_id in ingested_ids:
            skipped += 1
            continue
        print(f"• {file.get('name', '[Untitled]')} ({file_id})")
        if save_markdown:
            save_file_as_markdown(service, file)
        ingested_ids.add(file_id)
        saved += 1

    save_ingested_ids(ingested_ids)
    print(f"Saved: {saved}; skipped as already ingested: {skipped}")
    if saved and save_markdown:
        run_gbrain_import()
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Google Drive file metadata into Personal Brain")
    parser.add_argument("--max-results", type=int, default=100, help="Maximum files to fetch (default: 100)")
    parser.add_argument("--folder-id", help="Only list files directly inside this Drive folder")
    parser.add_argument("--modified-after", type=validate_rfc3339, help="Only list files modified after this ISO 8601 time")
    parser.add_argument("--query", help="Additional raw Drive API query, e.g. mimeType = 'application/pdf'")
    parser.add_argument("--no-save", action="store_true", help="List matching files without writing markdown")
    args = parser.parse_args()
    if args.max_results < 1:
        parser.error("--max-results must be at least 1")
    query = build_query(args.folder_id, args.modified_after, args.query)
    try:
        ingest_files(args.max_results, query, save_markdown=not args.no_save)
    except (ValueError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
