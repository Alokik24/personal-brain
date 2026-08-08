#!/usr/bin/env python3
"""
Gmail ingestion script using Google API Python Client with OAuth2.
Reads credentials from environment variables: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN
Ingests emails as markdown files with YAML frontmatter.
Maintains a local ingested_ids.json to skip already-fetched messages.
"""

import os
import base64
import json
import subprocess
import re
from typing import Optional, Set
from pathlib import Path
from datetime import datetime
from email.mime.text import MIMEText

from dotenv import load_dotenv
import frontmatter
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# Load environment variables from .env file
load_dotenv()

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Output directories and files
EMAILS_OUTPUT_DIR = Path(__file__).parent.parent / 'brain-source' / 'emails'
INGESTED_IDS_FILE = Path(__file__).parent.parent / 'ingested_ids.json'


def get_ingested_ids() -> Set[str]:
    """
    Load previously ingested message IDs from ingested_ids.json.
    
    Returns:
        Set of message IDs already ingested
    """
    if not INGESTED_IDS_FILE.exists():
        return set()
    
    try:
        with open(INGESTED_IDS_FILE, 'r') as f:
            data = json.load(f)
            return set(data.get('ids', []))
    except Exception as e:
        print(f"Warning: Failed to load ingested IDs: {e}")
        return set()


def save_ingested_ids(ids: Set[str]) -> None:
    """
    Save ingested message IDs to ingested_ids.json.
    
    Args:
        ids: Set of message IDs to save
    """
    try:
        with open(INGESTED_IDS_FILE, 'w') as f:
            json.dump({
                'ids': sorted(list(ids)),
                'last_updated': datetime.now().isoformat()
            }, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save ingested IDs: {e}")


def get_credentials() -> Credentials:
    """
    Authenticate with Gmail API using OAuth2.
    Reads credentials from environment variables.
    
    Returns:
        Credentials object for Gmail API
        
    Raises:
        ValueError: If required environment variables are missing
    """
    client_id = os.getenv('GMAIL_CLIENT_ID')
    client_secret = os.getenv('GMAIL_CLIENT_SECRET')
    refresh_token = os.getenv('GMAIL_REFRESH_TOKEN')
    
    if not all([client_id, client_secret, refresh_token]):
        raise ValueError(
            "Missing required environment variables: "
            "GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN"
        )
    
    # Create credentials from refresh token
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES
    )
    
    # Refresh the token to get a valid access token
    try:
        credentials.refresh(Request())
    except RefreshError as e:
        raise RuntimeError(f"Failed to refresh Gmail credentials: {e}")
    
    return credentials


def get_gmail_service(credentials: Credentials):
    """
    Build and return Gmail API service.
    
    Args:
        credentials: Credentials object
        
    Returns:
        Gmail service object
    """
    return build('gmail', 'v1', credentials=credentials)


def list_messages(service, user_id: str = 'me', query: str = '', max_results: int = 10) -> list:
    """
    List messages from Gmail inbox.
    
    Args:
        service: Gmail service object
        user_id: User ID (default: 'me' for authenticated user)
        query: Gmail search query (e.g., 'is:unread', 'from:someone@example.com')
        max_results: Maximum number of messages to retrieve
        
    Returns:
        List of message metadata
    """
    try:
        results = service.users().messages().list(
            userId=user_id,
            q=query,
            maxResults=max_results
        ).execute()
        
        messages = results.get('messages', [])
        return messages
    except HttpError as e:
        print(f"An error occurred: {e}")
        return []


def get_message(service, user_id: str = 'me', message_id: str = '') -> Optional[dict]:
    """
    Get full message content from Gmail.
    
    Args:
        service: Gmail service object
        user_id: User ID (default: 'me')
        message_id: ID of the message to retrieve
        
    Returns:
        Message object with headers, payload, etc.
    """
    try:
        message = service.users().messages().get(
            userId=user_id,
            id=message_id,
            format='full'
        ).execute()
        return message
    except HttpError as e:
        print(f"An error occurred: {e}")
        return None


def decode_message_body(message: dict) -> str:
    """
    Extract and decode message body from Gmail message object.
    Handles multipart messages and returns plaintext body.
    
    Args:
        message: Message object from Gmail API
        
    Returns:
        Decoded message body text (plaintext)
    """
    try:
        if 'parts' in message['payload']:
            # Multipart message - prefer text/plain
            parts = message['payload']['parts']
            
            # Try text/plain first
            text_part = next(
                (part for part in parts if part['mimeType'] == 'text/plain'),
                None
            )
            if text_part and 'body' in text_part and 'data' in text_part['body']:
                return base64.urlsafe_b64decode(text_part['body']['data']).decode('utf-8')
            
            # Fallback to text/html if no text/plain
            html_part = next(
                (part for part in parts if part['mimeType'] == 'text/html'),
                None
            )
            if html_part and 'body' in html_part and 'data' in html_part['body']:
                html_content = base64.urlsafe_b64decode(html_part['body']['data']).decode('utf-8')
                # Clean HTML tags
                return clean_html(html_content)
                
        elif 'body' in message['payload'] and 'data' in message['payload']['body']:
            # Simple message
            body_data = base64.urlsafe_b64decode(message['payload']['body']['data']).decode('utf-8')
            # Check if it's HTML or plaintext
            if body_data.strip().startswith('<'):
                return clean_html(body_data)
            return body_data
    except Exception as e:
        print(f"  Warning: Error decoding message body: {e}")
    
    return ""


def clean_html(html_text: str) -> str:
    """
    Convert HTML to plaintext by removing tags and decoding entities.
    
    Args:
        html_text: HTML content
        
    Returns:
        Cleaned plaintext content
    """
    # Remove script and style tags
    text = re.sub(r'<script[^>]*>.*?</script>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # Replace common HTML tags with newlines/spaces
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</tr>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</td>', ' ', text, flags=re.IGNORECASE)
    
    # Remove all remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Decode HTML entities
    import html as html_module
    text = html_module.unescape(text)
    
    # Clean up whitespace
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join([line for line in lines if line])  # Remove empty lines
    
    return text.strip()


def get_message_headers(message: dict) -> dict:
    """
    Extract message headers.
    
    Args:
        message: Message object from Gmail API
        
    Returns:
        Dictionary of message headers
    """
    headers = {}
    for header in message['payload']['headers']:
        headers[header['name']] = header['value']
    return headers


def generate_gmail_link(message_id: str) -> str:
    """
    Generate Gmail web link for a message.
    
    Args:
        message_id: Gmail message ID
        
    Returns:
        Gmail web URL
    """
    return f"https://mail.google.com/mail/u/0/#inbox/{message_id}"


def save_email_as_markdown(
    message: dict,
    thread_id: str,
    message_id: str,
    headers: dict,
    body: str,
    output_dir: Path = EMAILS_OUTPUT_DIR
) -> Optional[Path]:
    """
    Save email as markdown file with YAML frontmatter.
    
    Args:
        message: Full message object from Gmail API
        thread_id: Gmail thread ID
        message_id: Gmail message ID
        headers: Extracted message headers dict
        body: Email body (plaintext)
        output_dir: Directory to save markdown files
        
    Returns:
        Path to saved file, or None if failed
    """
    try:
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create filename: <threadId>-<messageId>.md
        filename = f"{thread_id}-{message_id}.md"
        filepath = output_dir / filename
        
        # Extract headers
        subject = headers.get('Subject', '[No Subject]')
        from_addr = headers.get('From', '[Unknown]')
        to_addr = headers.get('To', '[Unknown]')
        date_str = headers.get('Date', '')
        
        # Parse date to ISO format if possible
        try:
            from email.utils import parsedate_to_datetime
            date_obj = parsedate_to_datetime(date_str)
            date_iso = date_obj.isoformat()
        except Exception:
            date_iso = date_str
        
        # Create frontmatter
        post = frontmatter.Post(body.strip())
        post.metadata = {
            'from': from_addr,
            'to': to_addr,
            'subject': subject,
            'date': date_iso,
            'thread_id': thread_id,
            'gmail_id': message_id,
            'gmail_link': generate_gmail_link(message_id),
            'source': 'gmail'
        }
        
        # Write markdown file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(frontmatter.dumps(post))
        
        return filepath
        
    except Exception as e:
        print(f"  Error saving email to markdown: {e}")
        return None


def run_gbrain_import() -> bool:
    """
    Run gbrain import on the emails directory, including Git-ignored files.

    Email exports are intentionally Git-ignored because they contain private
    data. GBrain normally respects .gitignore, so the flag is required to
    index these local files without making them trackable by Git.
    
    Returns:
        True if import succeeded, False otherwise
    """
    try:
        print(f"\nImporting emails into gbrain...")
        result = subprocess.run(
            ['gbrain', 'import', str(EMAILS_OUTPUT_DIR), '--include-gitignored'],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            print(f"✓ gbrain import completed successfully")
            return True
        else:
            print(f"⚠ gbrain import completed with warnings:")
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)
            return False
    except FileNotFoundError:
        print(f"⚠ gbrain command not found. Install gbrain to auto-import emails.")
        return False
    except subprocess.TimeoutExpired:
        print(f"⚠ gbrain import timed out")
        return False
    except Exception as e:
        print(f"⚠ Failed to run gbrain import: {e}")
        return False


def ingest_emails(
    max_results: int = 10,
    query: str = 'newer_than:6m',
    save_markdown: bool = True
) -> int:
    """
    Main function to ingest emails from Gmail.
    
    Args:
        max_results: Maximum number of emails to ingest
        query: Gmail search query (default: emails from last 6 months)
        save_markdown: Whether to save emails as markdown files
        
    Returns:
        Number of successfully ingested emails
    """
    try:
        # Load previously ingested IDs
        ingested_ids = get_ingested_ids()
        print(f"Previously ingested: {len(ingested_ids)} emails")
        
        # Authenticate
        print("Authenticating with Gmail API...")
        credentials = get_credentials()
        
        # Build service
        service = get_gmail_service(credentials)
        
        # List messages
        print(f"Fetching messages matching: '{query}'...")
        messages = list_messages(service, query=query, max_results=max_results)
        
        if not messages:
            print("No new messages found.")
            return 0
        
        print(f"Found {len(messages)} messages matching query.\n")
        
        successful = 0
        skipped = 0
        
        # Process each message
        for idx, msg in enumerate(messages, 1):
            message_id = msg['id']
            thread_id = msg.get('threadId', 'unknown')
            
            # Skip if already ingested
            if message_id in ingested_ids:
                skipped += 1
                continue
            
            print(f"[{idx}/{len(messages)}] Processing message {message_id[:8]}...")
            
            # Get full message
            full_message = get_message(service, message_id=message_id)
            if not full_message:
                print(f"  ✗ Failed to fetch")
                continue
            
            # Extract headers
            headers = get_message_headers(full_message)
            subject = headers.get('Subject', '[No Subject]')
            from_addr = headers.get('From', '[Unknown]')
            
            print(f"  • {subject}")
            print(f"    From: {from_addr}")
            
            # Extract body (don't log it)
            body = decode_message_body(full_message)
            
            # Save as markdown
            if save_markdown:
                filepath = save_email_as_markdown(
                    full_message,
                    thread_id,
                    message_id,
                    headers,
                    body
                )
                if filepath:
                    print(f"  ✓ Saved")
                    successful += 1
                    ingested_ids.add(message_id)
                else:
                    print(f"  ✗ Failed to save")
            else:
                successful += 1
                ingested_ids.add(message_id)
            
            print()
        
        # Save updated ingested IDs
        save_ingested_ids(ingested_ids)
        
        print(f"\n{'='*60}")
        print(f"Ingestion Summary")
        print(f"{'='*60}")
        print(f"✓ Successfully ingested: {successful}")
        print(f"⊘ Skipped (already ingested): {skipped}")
        print(f"Total in database: {len(ingested_ids)}")
        print(f"{'='*60}")
        
        # Run gbrain import
        if successful > 0:
            run_gbrain_import()
        
        return successful
        
    except ValueError as e:
        print(f"Configuration error: {e}")
        exit(1)
    except RuntimeError as e:
        print(f"Authentication error: {e}")
        exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        exit(1)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Ingest emails from Gmail and save as markdown files'
    )
    parser.add_argument(
        '--max-results',
        type=int,
        default=10,
        help='Maximum number of emails to ingest (default: 10)'
    )
    parser.add_argument(
        '--query',
        type=str,
        default='newer_than:6m',
        help='Gmail search query (default: "newer_than:6m" - emails from last 6 months)'
    )
    parser.add_argument(
        '--no-save',
        action='store_true',
        help='Fetch emails but do not save as markdown files'
    )
    
    args = parser.parse_args()
    ingest_emails(
        max_results=args.max_results,
        query=args.query,
        save_markdown=not args.no_save
    )
