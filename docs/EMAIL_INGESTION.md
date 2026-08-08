# Email Ingestion Guide

## Quick Reference

### Basic Usage

**Ingest emails from the last 6 months (default):**

```bash
cd /home/keshu/personal_brain
source .venv/bin/activate
python3 scripts/ingest_gmail.py
```

**Ingest unread emails:**

```bash
python3 scripts/ingest_gmail.py --query "is:unread"
```

**Ingest recent emails with attachments:**

```bash
python3 scripts/ingest_gmail.py --query "has:attachment AND newer_than:2w" --max-results 20
```

### Output Structure

Emails are saved to `./brain-source/emails/` with filename format: `<threadId>-<messageId>.md`

Example:

```
brain-source/emails/
├── thread_abc123-msg_xyz789.md
├── thread_def456-msg_uvw012.md
└── thread_ghi789-msg_rst345.md
```

### Markdown File Format

Each file contains YAML frontmatter followed by the email body:

```markdown
---
from: sender@example.com
to: recipient@example.com
subject: Important Update
date: 2024-08-08T14:30:00+00:00
thread_id: thread_abc123
gmail_id: msg_xyz789
gmail_link: https://mail.google.com/mail/u/0/#inbox/msg_xyz789
source: gmail
---

# Email Body

This is the plaintext content of the email.

Multiple paragraphs and formatting are preserved.
```

### Common Workflows

**1. Ingest all unread emails from last week:**

```bash
python3 scripts/ingest_gmail.py --query "is:unread AND newer_than:1w" --max-results 50
```

**2. Ingest emails from a specific person:**

```bash
python3 scripts/ingest_gmail.py --query "from:boss@company.com"
```

**3. Ingest starred emails:**

```bash
python3 scripts/ingest_gmail.py --query "is:starred" --max-results 100
```

**4. Ingest with complex filter:**

```bash
python3 scripts/ingest_gmail.py \
  --query "from:team@company.com AND has:attachment AND newer_than:1m" \
  --max-results 30
```

**5. Just fetch emails without saving:**

```bash
python3 scripts/ingest_gmail.py --query "from:newsletter@example.com" --no-save
```

## Ask Questions About Ingested Mail

The Tier-1 Gmail answer flow works on the markdown files under
`brain-source/emails/`. It combines exact-term matching (especially useful for
names, amounts, and statuses) with a concise, source-backed answer.

```bash
source .venv/bin/activate
python scripts/ask_email.py "What is the pay of fixable Snorkel Task?"
```

After installing the project in editable mode, the equivalent command is:

```bash
brain-email "What is the pay of fixable Snorkel Task?"
```

Each answer prints the supporting email's subject, sender, date, and Gmail
link. This is intentionally separate from `gbrain search`: that command is
useful for inspecting semantic candidates, while `ask_email.py` returns the
user-facing answer.

### Verify the Answer Flow

```bash
# Runs the deterministic retrieval regression test
PYTHONPATH=src python -m unittest discover -s tests -v

# Runs against the email exports currently on disk
python scripts/ask_email.py "What is the pay of fixable Snorkel Task?"
```

For the current sample export, the latter should report `₹7,000 per submission
accepted on or before August 15, 2026` and cite the Crossing Hurdles / Snorkel
email.

## Gmail Search Query Reference

### Time-based

- `newer_than:1d` - Last 24 hours
- `newer_than:1w` - Last week
- `newer_than:1m` - Last month
- `newer_than:6m` - Last 6 months (default)
- `newer_than:1y` - Last year
- `before:2024-01-01` - Before specific date
- `after:2024-01-01` - After specific date

### Status

- `is:unread` - Unread emails
- `is:read` - Read emails
- `is:starred` - Starred emails
- `is:important` - Important emails
- `is:draft` - Draft emails
- `is:sent` - Sent emails

### Content

- `from:user@example.com` - From specific sender
- `to:user@example.com` - To specific recipient
- `subject:keyword` - Keyword in subject
- `body:keyword` - Keyword in body
- `has:attachment` - Has attachments
- `filename:pdf` - Specific file type

### Labels

- `label:name` - Emails with label
- `in:inbox` - In inbox
- `in:archive` - Archived
- `in:trash` - Trashed
- `in:spam` - Spam folder

### Operators

- `AND` - Both conditions (default)
- `OR` - Either condition
- `NOT` - Exclude condition
- Parentheses for grouping: `(from:x OR from:y) AND has:attachment`

## Tips & Tricks

### Setup for daily ingestion

```bash
# Add to crontab to ingest unread emails daily at 9 AM
0 9 * * * cd /home/keshu/personal_brain && source .venv/bin/activate && python3 scripts/ingest_gmail.py --query "is:unread" --max-results 50
```

### Process all ingested emails with gbrain

After ingesting emails, you can use gbrain to process them:

```bash
# Extract links between ingested emails
gbrain extract links --source db

# Query the ingested emails
gbrain think "What important information is in my recent emails?"

# Generate statistics
gbrain stats
```

### Next Steps

1. Ingest your emails: `python3 scripts/ingest_gmail.py`
2. Verify files in `brain-source/emails/`
3. Load into gbrain: `gbrain extract links --source db`
4. Query the brain: `gbrain think "summarize my recent emails"`
