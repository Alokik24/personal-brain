# Personal Brain

A conversational personal knowledge assistant built for the SkillLayer SDE I take-home assignment.

Personal Brain connects Gmail and Google Drive, stores their data in [gbrain](https://github.com/garrytan/gbrain), and answers natural-language questions through a Streamlit chat interface.

The system supports both single-source questions and cross-source reasoning without hardcoded relationships between specific Gmail messages and Drive files.

## Architecture

```text
                    ┌─────────────────┐
                    │   Streamlit UI  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Query routing  │
                    └────┬─────┬──────┘
                         │     │
                 Email   │     │   Google Drive
                         │     │
                    ┌────▼─┐ ┌─▼──────┐
                    │Gmail │ │ Drive  │
                    │path  │ │ path   │
                    └────┬─┘ └──┬─────┘
                         │       │
                         └───┬───┘
                             │
                         Both queries
                             │
                      ┌──────▼──────┐
                      │    gbrain   │
                      │    think    │
                      └──────┬──────┘
                             │
                      ┌──────▼──────┐
                      │ LLM synthesis│
                      │ + citations │
                      └──────┬──────┘
                             │
                      ┌──────▼──────┐
                      │   Answer    │
                      └─────────────┘
````

### Query paths

**Email**

Questions selected under `Email` use the Gmail-specific retrieval path.

**Google Drive**

Questions selected under `Google Drive` use the Drive-specific retrieval path.

**Both**

Questions requiring information across Gmail and Drive are sent to:

```bash
gbrain think "<question>"
```

GBrain performs retrieval and synthesis over the connected brain.

The application does not maintain a separate Gmail↔Drive correlation engine or hardcoded relationships between specific records.

## Requirements

* Python 3.10+
* Bun
* Google Cloud OAuth credentials
* Gmail API access
* Google Drive API access
* gbrain
* OpenRouter API key

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/Alokik24/personal-brain.git
cd personal-brain
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -e .
```

If installing manually:

```bash
pip install google-auth-oauthlib google-api-python-client python-frontmatter streamlit
```

### 4. Install gbrain

```bash
bun install -g github:garrytan/gbrain
```

Initialize the local brain:

```bash
gbrain init --pglite
```

Verify:

```bash
gbrain doctor
```

## Configuration

Set the required OAuth credentials and OpenRouter key in your environment.

```env
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
GMAIL_REFRESH_TOKEN=...

DRIVE_CLIENT_ID=...
DRIVE_CLIENT_SECRET=...
DRIVE_REFRESH_TOKEN=...

OPENROUTER_API_KEY=...
```

The GBrain models are configured through GBrain's own configuration.

For example:

```bash
gbrain config set chat_model openrouter:google/gemini-2.5-flash-lite
```

The exact model can be changed depending on the available OpenRouter credits.

Check the active routing with:

```bash
gbrain models
```

## Data ingestion

The prototype uses OAuth to retrieve data from the connected Google services.

Gmail and Drive records are normalized and ingested into the GBrain knowledge store.

After ingestion, verify that the brain contains the expected records:

```bash
gbrain search "SkillLayer take-home"
```

or:

```bash
gbrain search "Backend Engineer assessment"
```

## Running the application

Start the Streamlit interface:

```bash
PYTHONPATH=src streamlit run src/ui/app.py
```

The UI provides three search modes:

* **Email** — Gmail questions
* **Google Drive** — Drive questions
* **Both** — cross-source questions using GBrain

## Example queries

### Tier 1 — single-source

Gmail:

> Find the email from Acme Technologies about the Backend Engineer assessment.

Drive:

> What does the Acme Technologies Backend Engineer assessment ask me to do?

These demonstrate conversational answers grounded in a single connected source.

### Tier 2 — cross-source

> What jobs have I applied to, and what's my status on each, including my take-home submission?

This requires information from multiple sources and is handled through GBrain's cross-source retrieval and synthesis.

Another example:

> Did I ever send Priya the contract draft, and did she reply?

This combines evidence about the contract document with email context and demonstrates that the system is not hardcoded specifically for the SkillLayer example.

## Validation

The prototype was tested through the Streamlit UI and directly through GBrain.

Tier-1 validation confirmed that:

* Gmail can retrieve the relevant Acme Technologies assessment email.
* Drive can retrieve the corresponding assessment document.

Tier-2 validation confirmed that GBrain can retrieve and synthesize evidence across Gmail and Drive for questions such as the job-application and contract examples.

The system is designed to avoid fabricating information. When the connected data does not contain enough evidence, the answer may explicitly report a gap instead of asserting an unsupported conclusion.

## Project structure

```text
personal-brain/
├── README.md
├── pyproject.toml
├── .env
│
├── scripts/
│   ├── ingest_gmail.py
│   └── ingest_drive.py
│
├── src/
│   ├── api/
│   │   ├── email_search.py
│   │   ├── drive_search.py
│   │   ├── gbrain_think.py
│   │   └── chat.py
│   │
│   └── ui/
│       └── app.py
│
├── brain-source/
│   ├── emails/
│   └── drives/
│
└── tests/
```

## Design decisions

### Why gbrain?

GBrain provides the storage, semantic retrieval, and cross-source reasoning layer required by the assignment.

Using it directly avoids rebuilding a second retrieval/correlation system on top of the same data.

### Why separate Tier-1 paths?

Single-source questions do not require cross-source reasoning. The Gmail and Drive paths can therefore answer these questions directly and efficiently.

### Why use `gbrain think` for Both?

The assignment's main challenge is reasoning across multiple personal data sources.

For `Both` queries, GBrain is given the complete natural-language question and is responsible for retrieving relevant evidence and synthesizing the answer.

This keeps the application layer small and avoids hardcoded rules such as:

```text
if email.company == drive.company:
    correlate()
```

The relationships are discovered from the indexed data and the question itself.

## Limitations

This is a prototype rather than a production personal-data platform.

Known limitations include:

* Retrieval quality depends on the data currently ingested into GBrain.
* Incomplete source data can produce incomplete answers.
* Ambiguous relationships may not always be resolved correctly.
* OAuth refresh and production authentication are outside the scope of this prototype.
* The current deployment is intended primarily for local demonstration.

## Assignment alignment

The prototype demonstrates:

* Two connected personal tools: Gmail and Google Drive
* OAuth-based ingestion
* GBrain-backed storage
* A conversational Streamlit interface
* Single-source Tier-1 retrieval
* Cross-source Tier-2 reasoning
* Grounded answers with source citations
* An SDD documenting the intended system and implementation decisions

## References

* [gbrain](https://github.com/garrytan/gbrain)
* [Gmail API](https://developers.google.com/gmail/api)
* [Google Drive API](https://developers.google.com/drive/api)
* [Streamlit](https://streamlit.io/)
* [OpenRouter](https://openrouter.ai/)