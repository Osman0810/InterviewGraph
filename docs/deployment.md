# Production deployment

InterviewGraph is deployed as two services: a Next.js frontend on Vercel and a FastAPI API on Railway. The API connects to PostgreSQL on Railway or Neon and is the only component that receives AI-provider credentials.

```text
Browser → Vercel (Next.js) → Railway (FastAPI) → Gemini or OpenAI
                              └──────────────→ PostgreSQL
```

## Deployment order

1. Create a PostgreSQL database.
2. Deploy the FastAPI service.
3. Configure backend environment variables and secrets.
4. Run Alembic migrations.
5. Verify the API health endpoint.
6. Deploy the Next.js frontend.
7. Set `NEXT_PUBLIC_API_URL` to the public API URL and redeploy the frontend.
8. Test a Gemini-pinned session, if Gemini is configured.
9. Test an OpenAI-pinned session, if OpenAI is configured.
10. Confirm provider pinning by changing a global default only in a non-production environment and verifying an existing session keeps its stored provider/model.
11. Test **Delete Session Data** and verify the session’s related records are removed.

Do not use real candidate résumés or job descriptions for initial smoke tests.

## 1. Provision PostgreSQL

### Railway PostgreSQL

Create a PostgreSQL service in the same Railway project as the API. Railway exposes a connection URL that can be referenced by the FastAPI service as `DATABASE_URL`.

### Neon PostgreSQL

Create a Neon database and use its pooled PostgreSQL connection string for `DATABASE_URL`. Ensure the URL is compatible with SQLAlchemy’s psycopg dialect:

```text
postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require
```

Use one production database per environment. Do not reuse a local development database.

## 2. Deploy FastAPI to Railway

Create a Railway service from the GitHub repository.

- **Root directory:** `api`
- **Builder:** Dockerfile
- **Dockerfile:** `api/Dockerfile` when Railway resolves it from the repository root, or `Dockerfile` when the service root is `api`
- **Health check path:** `/health`
- **Health check timeout:** allow enough time for database connection startup (for example, 30 seconds)

The production image:

- runs Uvicorn on Railway’s injected `PORT` (or port 8000 locally);
- enables proxy headers for the Railway reverse proxy;
- runs as a non-root user;
- includes Alembic files so migrations can run from the deployed image;
- does not copy local virtual environments, test artifacts, databases, or logs into the image.

The service command is supplied by the Dockerfile:

```text
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'
```

The API must be reachable at `https://<railway-api-domain>/health` before deploying the frontend.

## 3. Configure backend environment variables

Set these in Railway’s service variables. They are server-side secrets and must never be set in Vercel or any `NEXT_PUBLIC_*` variable.

| Variable | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` | Yes | Railway PostgreSQL reference or Neon SQLAlchemy psycopg URL. |
| `AI_PROVIDER` | Yes | Default provider for newly created sessions: `gemini` or `openai`. |
| `ALLOW_PROVIDER_FALLBACK` | Yes | Keep `false`; automatic cross-provider fallback is not implemented. |
| `GEMINI_API_KEY` | Gemini only | Configure when Gemini can be selected. |
| `GEMINI_MODEL` | Gemini only | Server-selected Gemini model. |
| `OPENAI_API_KEY` | OpenAI only | Configure when OpenAI can be selected. |
| `OPENAI_MODEL` | OpenAI only | Server-selected OpenAI model. |
| `FRONTEND_ORIGIN` | Yes | Exact production Vercel origin, e.g. `https://interviewgraph.vercel.app`. |
| `INTERVIEW_QUESTION_LIMIT` | Optional | Defaults to `12`. |
| `API_RATE_LIMIT_REQUESTS` | Optional | Defaults to `120` per rate-limit window for one API instance. |
| `API_RATE_LIMIT_WINDOW_SECONDS` | Optional | Defaults to `60`. |

### Supported provider configurations

**Gemini only**

```text
AI_PROVIDER=gemini
GEMINI_API_KEY=<secret>
GEMINI_MODEL=gemini-3.8-flash
ALLOW_PROVIDER_FALLBACK=false
```

Leave `OPENAI_API_KEY` unset. A user selecting OpenAI receives a safe configuration error; the API still starts.

**OpenAI only**

```text
AI_PROVIDER=openai
OPENAI_API_KEY=<secret>
OPENAI_MODEL=gpt-4o-mini
ALLOW_PROVIDER_FALLBACK=false
```

Leave `GEMINI_API_KEY` unset. A user selecting Gemini receives a safe configuration error; the API still starts.

**Both providers**

Set both keys and both model variables. Gemini remains the frontend’s default selection. A session stores its selected `ai_provider` and server-chosen `ai_model`; later operations use those pinned values even if global defaults change.

There is no automatic Gemini-to-OpenAI or OpenAI-to-Gemini fallback. In particular, OpenAI must never become a paid fallback. Keep `ALLOW_PROVIDER_FALLBACK=false` unless fallback behavior is explicitly designed, implemented, reviewed, and approved in a future change.

## 4. Run database migrations

Run migrations once for each deployment that introduces a migration, before routing production traffic to code that requires it:

```sh
cd /app
alembic upgrade head
```

On Railway, run this as a one-off command or release job using the deployed API image and its production `DATABASE_URL`. Do not run migrations in every web-process startup: multiple replicas could race. Back up production data before destructive schema changes, and use expand/contract migrations for changes requiring multi-release compatibility.

## 5. Verify API health

After variables and migrations are in place:

```sh
curl -fsS https://<railway-api-domain>/health
```

Expected result:

```json
{"status":"ok","database":"connected"}
```

Failures should be investigated from Railway’s protected service logs; do not paste keys, prompts, résumés, or provider responses into tickets or logs.

## 6. Deploy Next.js to Vercel

Import the same GitHub repository into Vercel.

- **Root directory:** `web`
- **Framework preset:** Next.js
- **Install command:** `npm install` (Vercel’s default is also suitable)
- **Build command:** `npm run build`
- **Output directory:** leave unset for Next.js

Set exactly one production frontend variable:

```text
NEXT_PUBLIC_API_URL=https://<railway-api-domain>
```

`NEXT_PUBLIC_*` values are embedded in the browser bundle at build time. Never put `GEMINI_API_KEY`, `OPENAI_API_KEY`, provider model names, database URLs, or backend-only settings in Vercel’s frontend variables. Redeploy after changing `NEXT_PUBLIC_API_URL`.

Set `FRONTEND_ORIGIN` on Railway to the resulting Vercel production origin exactly (no path). Preview deployments need either a separate API environment or an explicitly permitted preview origin; do not broaden CORS to `*` in production.

## Security and reliability checklist

- Keep `.env`, `.env.local`, uploaded files, logs, SQLite files, and virtual environments out of Git. Only empty placeholders belong in `.env.example`.
- Use Railway/Vercel secret stores for credentials; never paste them into source code, GitHub Actions logs, browser variables, or client requests.
- The browser talks only to FastAPI. Gemini/OpenAI keys, prompts, résumé text, candidate answers, and raw provider responses remain backend-only and are not logged.
- CORS permits only the configured `FRONTEND_ORIGIN`; configure it before exposing the Vercel UI.
- Production API errors are sanitized. Provider 429, 503, 504, and malformed structured-output failures have safe client messages and bounded retries where appropriate.
- The built-in API rate limiter is process-local. For multiple Railway replicas, enforce a shared rate limit at a gateway or add a Redis-backed limiter before relying on it for abuse protection.
- `DELETE /sessions/{id}` cascades through the session’s job description, résumé text, competencies, evidence, questions, answers, evaluations, scores, study plans, and replays. Verify this on non-sensitive test data after deployment.

## References

- [Vercel environment variables](https://examples.vercel.com/kb/guide/how-to-add-vercel-environment-variables)
- [Vercel monorepo root directory guidance](https://examples.vercel.com/academy/nextjs-foundations/multi-app-routing)
- [Railway FastAPI deployment](https://docs.railway.com/guides/fastapi)
- [Railway PostgreSQL](https://docs.railway.com/databases/postgresql)
- [Railway health checks](https://docs.railway.com/deployments/healthchecks)
- [Railway variables and reference variables](https://docs.railway.com/variables)
