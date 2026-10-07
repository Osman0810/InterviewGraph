# InterviewGraph Architecture

## System shape

```text
Browser (Next.js)
        |
        | HTTPS API requests; no provider credentials
        v
FastAPI
  |-- document parsing and validation
  |-- session and interview orchestration
  |-- deterministic scoring
  |-- PostgreSQL persistence
  |-- AIProvider resolver
        |                 |
        v                 v
GeminiProvider       OpenAIProvider
google-genai SDK     OpenAI Responses API
```

The browser communicates only with FastAPI. Gemini and OpenAI credentials are backend-only and must never use `NEXT_PUBLIC_*` variables.

## Provider boundary and pinning

`AIProvider` is a provider-neutral structured-generation protocol. `GeminiProvider` and `OpenAIProvider` implement it with Pydantic-backed structured output, bounded retries, safe error translation, and prompt-safe logging.

At session creation, the API:

1. accepts only the provider name (`gemini` or `openai`),
2. validates that its server-side credentials are configured,
3. selects the server-configured model,
4. persists `InterviewSession.ai_provider` and `InterviewSession.ai_model`.

Every AI route resolves its provider from those pinned fields. The global `AI_PROVIDER` default affects only new sessions. `ALLOW_PROVIDER_FALLBACK=false` is the default and no cross-provider fallback is implemented.

## AI workflows

The following services receive `AIProvider`, never a concrete provider:

- JD competency extraction
- résumé evidence analysis
- interview question generation
- answer evaluation and replay evaluation
- targeted study-plan generation

The application, not the provider, chooses competency coverage, question sequence, difficulty, question type, and interview completion.

## Deterministic assessment logic

Providers can return structured competency evidence, natural-language questions, and answer-evaluation signals. `ScoringService` alone computes final competency scores, confidence, gap priority, and overall readiness from persisted evidence and evaluations. In résumé-only mode, scores remain explicitly evidence-based rather than verified technical knowledge.

## Data flow

1. The frontend submits a job description and résumé source.
2. FastAPI validates uploads and extracts PDF/DOCX/TXT text locally. Original uploads are not retained.
3. The session-pinned provider produces a competency graph and résumé evidence.
4. The user selects Start Interview or Skip Interview.
5. Interview mode persists questions, answers, and evaluations; the deterministic engine selects each next question.
6. Results are read from PostgreSQL without a provider call. Study-plan generation is explicit and persists only the latest structured plan.

## Reliability and security

- Provider timeouts, rate limits, service unavailability, and invalid structured output map to safe API errors.
- Retries are bounded and provider-owned; authentication, malformed requests, quota/billing failures, and structured validation failures do not retry blindly.
- Provider prompts, raw model responses, résumé text, candidate answers, and API keys are not logged.
- SQLAlchemy transactions roll back on failures. Session deletion cascades to related assessment records.
- Automated tests replace providers with fakes and make no real AI calls.

## Local deployment

Docker Compose runs PostgreSQL and the FastAPI API. Next.js can run locally with npm. Alembic manages schema evolution, including the session provider/model migration. `.env.example` documents non-secret placeholders and `.env` remains untracked.
