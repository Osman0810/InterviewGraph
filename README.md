# InterviewGraph

InterviewGraph is an AI-assisted technical interview simulator. It turns a job description into a competency graph, maps résumé evidence to that graph, and produces either an adaptive interview assessment or a clearly labeled résumé-evidence analysis.

## What it does

1. Accepts a job description as pasted text or TXT.
2. Accepts a résumé as pasted text, PDF, or DOCX; files are parsed locally and are not permanently stored.
3. Extracts role competencies and résumé evidence using a server-side AI provider.
4. Lets the user choose an adaptive interview or résumé-only analysis.
5. Produces deterministic competency scores, an overall-readiness score, a knowledge-gap map, strengths, priority gaps, feedback, replay practice, and an optional targeted study plan.

Résumé-only results deliberately measure available résumé evidence, not verified knowledge.

## AI providers

The browser chooses either `gemini` or `openai` before creating a session. It never receives API keys or selects models.

- **Gemini** uses the official `google-genai` SDK.
- **OpenAI** uses the official `openai` Python SDK and the Responses API.
- The API resolves the server-configured model and persists both `ai_provider` and `ai_model` on each `InterviewSession`.
- Every later AI operation resolves that pinned provider/model. Changing global defaults never changes an existing session.
- `ALLOW_PROVIDER_FALLBACK=false` is the default. There is no automatic cross-provider fallback.

Both providers implement the common `AIProvider` structured-generation boundary. The provider is used for competency extraction, résumé evidence, question language, answer evaluation, and study-plan generation.

## Scoring

AI providers supply structured evidence and evaluations only. Final competency percentages, confidence, gap priority, and overall readiness are deterministic Python calculations in `ScoringService`; no provider generates those final scores.

## Architecture

```text
Browser (Next.js)
      |
      v
FastAPI
      |
      v
AIProvider ── GeminiProvider
      └────── OpenAIProvider
      |
      v
PostgreSQL
```

The frontend communicates only with FastAPI. Secrets and provider prompts remain backend-only. See [docs/architecture.md](docs/architecture.md) for the fuller system design.

## Local setup

Prerequisites: Node.js/npm, Python, PostgreSQL or Docker Compose.

1. Copy `.env.example` to `.env` and set the values required for the provider(s) you plan to use.
2. Create the backend environment and install dependencies:

   ```powershell
   cd api
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m alembic upgrade head
   ```

3. Start PostgreSQL and FastAPI with Docker Compose, or run FastAPI locally:

   ```powershell
   docker compose up --build
   # or from api/
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

4. In another shell, start Next.js:

   ```powershell
   cd web
   npm install
   npm run dev
   ```

`web/.env.example` contains only `NEXT_PUBLIC_API_BASE_URL`. Do not add provider credentials or model settings to browser-visible variables.

## Environment variables

Required local infrastructure settings:

- `DATABASE_URL`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `AI_PROVIDER` (`gemini` or `openai`)
- `ALLOW_PROVIDER_FALLBACK=false`
- `GEMINI_API_KEY`, `GEMINI_MODEL`
- `OPENAI_API_KEY`, `OPENAI_MODEL`
- `INTERVIEW_QUESTION_LIMIT`
- `FRONTEND_ORIGIN`, `API_RATE_LIMIT_REQUESTS`, `API_RATE_LIMIT_WINDOW_SECONDS`

Only configure the credentials for providers you intend to use. Session creation safely rejects a selected provider that is not configured.

## Testing and validation

Automated tests mock provider behavior and make zero real Gemini or OpenAI calls.

```powershell
cd api
.\.venv\Scripts\python.exe -m pytest -q

cd ..\web
npm run lint
npm run build
```

## Security notes

- `.env` and `.env.local` are ignored.
- Original uploaded files are parsed in memory and are not retained; extracted session text is removed with the session.
- API keys, full prompts, résumé text, candidate answers, and raw provider responses are not logged.
- Session deletion cascades through associated assessment data.
