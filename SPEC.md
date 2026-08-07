# Personal Brain Spec

## Problem statement

Build a personal knowledge assistant that can answer natural-language questions over a user’s own data by combining facts from multiple personal tools. The first prototype will focus on Gmail and Google Drive, using gbrain as the storage layer for normalized markdown pages. The system should support conversational answers rather than raw search dumps, with at least one cross-source query that joins information from both connectors.

## Non-goals

- Full production-grade authentication or OAuth refresh handling.
- Support for every possible connector in the first iteration.
- Perfect reasoning over ambiguous or incomplete data.
- Long-running autonomous workflows or agentic task execution beyond the basic retrieval-and-synthesis flow.

## Data model for markdown pages stored in gbrain

Each ingested artifact will be stored as a markdown page in gbrain with YAML frontmatter followed by content. The frontmatter is designed so that retrieval can be filtered and grouped by source and entity.

### Common frontmatter fields

- `source`: connector name, e.g. `gmail` or `drive`
- `source_id`: stable identifier from the external system
- `kind`: entity type, e.g. `email`, `attachment`, `file`, `thread`
- `title`: human-readable title
- `created_at`: timestamp in ISO 8601 format
- `updated_at`: timestamp in ISO 8601 format
- `participants`: list of people involved
- `labels`: list of tags or categories
- `related_ids`: list of IDs from other sources that are semantically related
- `summary`: short natural-language summary
- `raw_path`: optional reference for the original content location

### Gmail page schema

For Gmail, each message or thread will be stored as a page with frontmatter such as:

```yaml
---
source: gmail
source_id: "thread-123"
kind: thread
title: "Stripe failed payment"
created_at: "2026-08-01T09:30:00Z"
updated_at: "2026-08-01T09:45:00Z"
participants:
  - "stripe@example.com"
  - "user@example.com"
labels:
  - "finance"
  - "important"
related_ids:
  - "drive-file-456"
summary: "User received an email from Stripe about a failed payment and a follow-up thread."
---
```

The body content will include the parsed message subject, sender, recipients, snippet, and a small normalized transcript.

### Drive page schema

For Drive files, each file or attachment will be stored as a page with frontmatter such as:

```yaml
---
source: drive
source_id: "file-456"
kind: file
title: "take-home-submission.pdf"
created_at: "2026-08-02T14:00:00Z"
updated_at: "2026-08-02T14:00:00Z"
participants:
  - "user@example.com"
labels:
  - "submission"
  - "attachment"
related_ids:
  - "thread-123"
summary: "Submission file attached to a job application thread."
---
```

The body content will include the file name, mime type, parent folder context, and any extracted text when available.

## Ingestion approach

1. Authenticate to Gmail and Drive using OAuth credentials.
2. Fetch a selected set of relevant records from each connector.
3. Normalize each record into a markdown document with the required frontmatter fields.
4. Store each document in gbrain as a page with a deterministic title and metadata.
5. Optionally enrich records with links between Gmail and Drive artifacts when a file attachment is clearly associated with a thread or email.

The initial ingestion will be conservative and explicit. Only the records needed for the demo queries will be imported first, with later iterations expanding coverage.

## Query flow

1. The user enters a natural-language question in the chat UI.
2. The app sends the question to the backend.
3. The backend uses gbrain search to retrieve relevant markdown pages from Gmail and Drive.
4. The backend passes the retrieved snippets and metadata to an LLM to synthesize a conversational answer.
5. The answer is returned to the chat UI and displayed as a chat response.

The core retrieval pattern is:

- `gbrain search -> relevant pages`
- `LLM reasoning over retrieved context`
- `chat UI rendering`

The system should prefer grounding every answer in actual retrieved evidence and avoid inventing missing facts.

## Demo queries

1. Tier 1 example: "What’s on my calendar tomorrow?"
2. Tier 2 example: "What jobs have I applied to, and what’s my status on each, including my take-home submission?"
3. Tier 2 example: "Did I ever send Priya the contract draft, and did she reply?"

## Implementation notes for this milestone

- The spec is written first and will guide all implementation work.
- The initial prototype will prioritize Gmail and Drive integration.
- The first working demo should show one tier-1 query and at least one tier-2 query.
