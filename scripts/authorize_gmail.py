#!/usr/bin/env python3
"""Run a one-time OAuth flow to create a Gmail-scoped refresh token.

Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET first.
"""

from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow


load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main() -> None:
    argparse.ArgumentParser(
        description="Open a browser flow and print a Gmail-scoped refresh token"
    ).parse_args()

    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise SystemExit(
            "Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env "
            "before authorizing."
        )

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    credentials = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
        authorization_prompt_message=(
            "Open this URL in your browser to authorize Gmail access:\n{url}\n"
        ),
        success_message=(
            "Gmail authorization completed. "
            "You can close this browser tab."
        ),
    )

    if not credentials.refresh_token:
        raise SystemExit(
            "Google did not return a refresh token. "
            "Revoke the app and try again."
        )

    print("\nAdd this value to .env (do not commit it):")
    print(f"GMAIL_REFRESH_TOKEN={credentials.refresh_token}")


if __name__ == "__main__":
    main()