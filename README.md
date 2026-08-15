# Personal Brain

A personal knowledge management system using **gbrain** (local PGLite) and Gmail ingestion with OAuth2.

## Overview

This project integrates:

- **gbrain**: A local knowledge brain powered by PGLite (Postgres in SQLite)
- **Gmail API**: OAuth2-based email ingestion
- **Python backend**: Gmail ingestion script and API services

## Quick Start

### Prerequisites

- Python 3.14+
- bun (JavaScript runtime)
- Gmail OAuth2 credentials (Client ID, Client Secret, Refresh Token)

### 1. Setup Virtual Environment

```bash
# Create virtual environment (if not already done)
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate
```

### 2. Install gbrain

```bash
bun install -g github:garrytan/gbrain
```

### 3. Initialize Local Brain

```bash
gbrain init --pglite
```

This creates:

- Local brain at `~/.gbrain/brain.pglite`
- PGLite database (no server needed)
- Embedding model: `openrouter:openai/text-embedding-3-small`
- Chat model: `openrouter:anthropic/claude-sonnet-4.6`

**Verify installation:**

```bash
gbrain doctor
```

Expected output: All core health checks ✓ (database, embeddings, schema, skills)

### 4. Install Python Dependencies

```bash
source .venv/bin/activate
pip install google-auth-oauthlib google-api-python-client python-frontmatter
```

## Configuration

### Environment Variables

Create or update `.env` with your Gmail OAuth2 credentials:

```env
# Gmail OAuth2 Credentials
GMAIL_CLIENT_ID=your_client_id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=your_client_secret
GMAIL_REFRESH_TOKEN=your_refresh_token

# Optional: API Keys for gbrain models
OPENROUTER_API_KEY=your_openrouter_key
# Optional override for conversational, source-grounded synthesis
OPENROUTER_MODEL=anthropic/claude-sonnet-4.6
# Explicit opt-in: model requests may incur API usage
PERSONAL_BRAIN_ENABLE_SYNTHESIS=true
```

When `OPENROUTER_API_KEY` and `PERSONAL_BRAIN_ENABLE_SYNTHESIS=true` are set,
Gmail and Drive answers are synthesized from only the retrieved local source
text. The prompt requires an explicit
"I don't know from the retrieved … records" response when the evidence does
not answer the question. Without a key or if the model call fails, the app uses
the deterministic local answer path instead. Spreadsheet totals always remain
deterministic.

### Drive authorization

Drive ingestion needs a refresh token authorized with the `drive.readonly`
scope. A Gmail-only token cannot list or export Drive files. Create a dedicated
Drive token once, then save the printed value as `DRIVE_REFRESH_TOKEN` in
`.env`:

```bash
source .venv/bin/activate
python scripts/authorize_drive.py
```

The browser flow uses `DRIVE_CLIENT_ID` / `DRIVE_CLIENT_SECRET`, falling back
to `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` if those values describe the same
OAuth client. Do not commit the resulting token.

### Getting Gmail OAuth2 Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable Gmail API
4. Create OAuth2 credentials (OAuth 2.0 Client IDs)
5. Generate refresh token using the `get_refresh_token.py` script (or manually via OAuth flow)

## Gmail Ingestion

### Script: `scripts/ingest_gmail.py`

Ingest emails from Gmail using OAuth2 and save them as markdown files with YAML frontmatter.

#### Usage

```bash
source .venv/bin/activate

# Ingest emails from last 6 months (default) and save as markdown
python3 scripts/ingest_gmail.py

# Ingest last 50 unread emails
python3 scripts/ingest_gmail.py --max-results 50 --query "is:unread"

# Ingest emails from specific sender
python3 scripts/ingest_gmail.py --query "from:user@example.com"

# Fetch emails without saving to files
python3 scripts/ingest_gmail.py --no-save

# Custom query and results
python3 scripts/ingest_gmail.py --max-results 100 --query "has:attachment"

# Help
python3 scripts/ingest_gmail.py --help
```

#### Features

- ✅ OAuth2 authentication via `google-auth-oauthlib`
- ✅ Gmail API client via `google-api-python-client`
- ✅ Credentials from environment variables
- ✅ Configurable search query (default: `newer_than:6m`)
- ✅ **Saves emails as markdown files** with YAML frontmatter
- ✅ Extract and decode email bodies (plaintext preferred, HTML fallback)
- ✅ Parse and include message headers
- ✅ CLI arguments for filtering and pagination

#### Markdown File Format

Emails are saved to `./brain-source/emails/<threadId>-<messageId>.md` with YAML frontmatter:

```markdown
---
from: sender@example.com
to: recipient@example.com
subject: Email Subject
date: 2024-08-08T10:30:00+00:00
thread_id: thread_abc123
gmail_id: message_xyz789
gmail_link: https://mail.google.com/mail/u/0/#inbox/message_xyz789
source: gmail
---

# Email Body

This is the plaintext content of the email.
Multipart messages default to plaintext, falling back to HTML if unavailable.
```

The frontmatter includes:

- **from**: Sender email address
- **to**: Recipient email address
- **subject**: Email subject line
- **date**: ISO 8601 formatted date
- **thread_id**: Gmail thread ID (for conversation grouping)
- **gmail_id**: Gmail message ID
- **gmail_link**: Direct link to email in Gmail
- **source**: Always "gmail" for ingested emails

#### Supported Gmail Queries

- `newer_than:6m` - Emails from last 6 months (default)
- `is:unread` - Unread emails
- `is:starred` - Starred emails
- `from:user@example.com` - Emails from specific sender
- `to:user@example.com` - Emails to specific recipient
- `subject:keyword` - Emails with keyword in subject
- `has:attachment` - Emails with attachments
- `before:2024-01-01` - Emails before date
- `after:2024-01-01` - Emails after date
- `label:name` - Emails with specific label
- `is:important` - Emails marked as important

Combine with operators: `is:unread AND from:user@example.com AND newer_than:1m`

## Ask Gmail questions

`gbrain search` is useful for exploring semantic matches, but it prints search
snippets. For a Tier-1 conversational, evidence-backed answer over the local
Gmail export, use:

```bash
source .venv/bin/activate
python scripts/ask_email.py "What is the pay of fixable Snorkel task?"
# or, after `pip install -e .`:
brain-email "What is the pay of fixable Snorkel task?"
```

For locally exported Drive files, use the equivalent Drive-only command:

```bash
python scripts/ask_drive.py "Where is my Snorkel take-home submission?"
# or, after `pip install -e .`:
brain-drive "Where is my Snorkel take-home submission?"
```

Both answer commands use hybrid retrieval: exact matches in the subject/sender/body are ranked
above broad semantic matches, then the best matching email sentence is returned
with links to the source messages. The same behaviour is available at
`POST /chat` with `{ "question": "..." }`, or through the Streamlit UI:

```bash
PYTHONPATH=src streamlit run src/ui/app.py
```

### Verify the Tier-1 flow

```bash
# Regression test: checks that exact terms rank the Snorkel payment email first
PYTHONPATH=src python -m unittest discover -s tests -v

# Verify against the locally ingested Gmail export
python scripts/ask_email.py "What is the pay of fixable Snorkel Task"
```

The expected answer from the current export is `₹7,000 per submission accepted
on or before August 15, 2026`. The response also includes a Gmail source link.

## Project Structure

```
personal_brain/
├── .env                          # Environment variables (credentials)
├── .venv/                        # Python virtual environment
├── pyproject.toml               # Python project config
├── README.md                    # This file
│
├── scripts/
│   ├── ingest_gmail.py         # Gmail OAuth2 ingestion script
│   └── ask_email.py            # Tier-1 Gmail question launcher
│
├── src/
│   ├── api/                    # Gmail retrieval and FastAPI endpoint
│   └── ui/                     # Streamlit chat UI
│
└── brain-source/
    └── emails/                 # Ingested email markdown files
```

## Brain Architecture

### PGLite Configuration

- **Engine**: PGLite (local Postgres, no server)
- **Location**: `~/.gbrain/brain.pglite`
- **Embeddings**: `openrouter:openai/text-embedding-3-small` (768-dim vectors)
- **Chat Model**: `openrouter:anthropic/claude-sonnet-4.6`
- **Skills**: 52 bundled skills loaded

### Key gbrain Commands

```bash
# Health check
gbrain doctor

# Query the brain
gbrain think "What do I know about X?"

# List pages
gbrain pages

# Extract links from pages
gbrain extract links --source db

# Extract timeline
gbrain extract timeline --source db

# View stats
gbrain stats
```

## Optional Features

### Link Extraction

Enhance the knowledge graph by extracting links between pages:

```bash
gbrain extract --stale
```

### Retrieval Reflex

Install policy skill for advanced retrieval optimization:

```bash
gbrain integrations install retrieval-reflex --target <host-repo>
```

### GStack (Coding Skills)

Install GStack for coding-specific skills:

```bash
git clone https://github.com/garrytan/gstack.git ~/.claude/skills/gstack
cd ~/.claude/skills/gstack && ./setup
```

### Subagent Features

For `gbrain dream`, `gbrain agent run`, and `gbrain autopilot`:

```bash
# Option 1: Set Anthropic API key
export ANTHROPIC_API_KEY=your_key

# Option 2: Enable gateway loop mode
gbrain config set agent.use_gateway_loop true
```

## Migration to Production

When ready to deploy beyond local development:

```bash
gbrain migrate --to supabase
```

This migrates the PGLite brain to a cloud-hosted Supabase Postgres instance.

## Development

### Activate Virtual Environment

```bash
cd /home/keshu/personal_brain
source .venv/bin/activate
```

### Add Python Dependencies

```bash
source .venv/bin/activate
pip install <package-name>
```

## Troubleshooting

### "No module named 'google'"

Ensure virtual environment is activated and dependencies are installed:

```bash
source .venv/bin/activate
pip install google-auth-oauthlib google-api-python-client
```

### Gmail Authentication Fails

Check environment variables:

```bash
echo $GMAIL_CLIENT_ID
echo $GMAIL_CLIENT_SECRET
echo $GMAIL_REFRESH_TOKEN
```

If missing, add to `.env` and reload:

```bash
source .env
```

### gbrain Brain Not Found

Ensure initialization is complete:

```bash
gbrain doctor
```

If brain is missing, reinitialize:

```bash
gbrain init --pglite
```

## Next Steps

- [ ] Implement email → brain page ingestion (parse and store as markdown)
- [ ] Build API endpoints for brain queries (`src/api/`)
- [ ] Create UI dashboard for brain exploration (`src/ui/`)
- [ ] Set up automated email sync (cron or webhook)
- [ ] Implement link extraction and timeline backfill
- [ ] Add retrieval reflex for semantic search
- [ ] Deploy to Supabase for production

## Resources

- [gbrain Documentation](https://github.com/garrytan/gbrain)
- [Google Gmail API](https://developers.google.com/gmail/api)
- [PGLite](https://pglite.io/)
- [OpenRouter API](https://openrouter.ai/)

## License

Personal project — All rights reserved.
