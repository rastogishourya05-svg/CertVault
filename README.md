# CertVault

Gmail PDF ingestion development code is now available behind a disabled live flag. See [pipeline setup and verified boundaries](docs/GMAIL_PIPELINE.md). No real mailbox scan or production deployment has been performed.

A private certificate vault built with Next.js/TypeScript/Tailwind/shadcn-style Radix components, FastAPI, and Celery/Redis. **Current runtime is loopback-only development, not a production release.** The main workspace uses isolated SQLite sessions/private local files and synthetic Gmail/Outlook samples. `/account` provides a separately configured, verified Supabase sign-in/private metadata slice. Do not upload real or untrusted documents.

## Start locally

Use Node 22+ (24 LTS recommended), pnpm 11, Python 3.13 and Docker Desktop. From the repository root:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
pnpm install --frozen-lockfile
docker compose -f infra/compose.yaml up -d redis
```

Start the API and frontend in separate terminals:

```powershell
.venv/Scripts/python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

```powershell
pnpm dev
```

Open [CertVault locally](http://127.0.0.1:3000). Start a demo session, connect a **sample** mailbox, then scan it. Three synthetic PDFs enter the vault; a 51 MiB sample waits for explicit approval at the default 50 MiB threshold. Repeat scans are idempotent. No external account is accessed. Demo mailbox scans run synchronously; a real Celery task boundary is separately smoke-tested against Redis.

The API listens only on loopback, checks Host/Origin, uses HttpOnly SameSite sessions, scopes all records to the session owner, and stores files outside the web root. `.local/` is ignored by Git. A demo session expires after 24 hours; this is not persistent production account authentication. Demo share/profile addresses are accessible only on this laptop.

## Checks

```powershell
.venv/Scripts/python -m ruff check apps tests scripts
.venv/Scripts/python -m ruff format --check apps tests scripts
.venv/Scripts/python -m pytest -q
pnpm lint
pnpm typecheck
pnpm test
pnpm build
# Install Playwright's browser once, or use an installed Chrome:
pnpm --filter web exec playwright install chromium
$env:PLAYWRIGHT_CHANNEL='chrome' # optional; omit to use bundled Chromium
pnpm e2e
$env:PYTHONPATH='.'
.venv/Scripts/python scripts/check-worker.py
```

E2E automatically starts and waits for app/API servers, or reuses running local servers. Tests use independent demo sessions and synthetic files. `pnpm build` uses Next's supported Webpack option because Turbopack's CSS subprocess failed on the development machine. Local Playwright traces are off due to a Windows cleanup stall; CI retains failure traces. Screenshots are saved under `docs/evidence/` at 1440px and 390px.

## Structure and production boundary

- `apps/web`: responsive workspace, onboarding, vault, approval inbox, connections, history, settings, sharing, profile and editable template caption studio.
- `apps/api`: validated requests, local owner-scoped store, deterministic size/dedupe policy, sample PDF extraction, isolated OAuth/provider/JWKS primitives.
- `apps/worker`: retry/backoff/rate-limited Celery sample sync task.
- `supabase/migrations`: production Postgres schema, ownership RLS, private token schema and private storage bucket. Applied to the authorized development project; the app runtime is still a local demo.
- `infra/sql`: disposable PostgreSQL ownership tests and a manual destructive development rollback.
- `infra`: development Docker services and a non-root API image template. The image fails closed until explicitly configured; it is not ready for production deployment.

See [implementation checkpoint](docs/IMPLEMENTATION_STATUS.md), [integration and deployment runbook](docs/OPERATIONS.md), and the authoritative [PRD](docs/PRD.md). Supabase sign-in/out, refresh, private metadata reads/favorites and preference writes have been tested against the approved development project. Registration/reset, document Storage HTTP flows, live verification of the new Gmail pipeline/Storage, OCR, safe link fetching and AI generation remain incomplete. Nothing has been deployed.

## Supabase development account slice

Open `/account` using the “Development account sign-in” link. Configuration is already present on the original development machine in ignored `.local/supabase.json`; its encryption key is never bundled in the web app. On a new machine, set the approved project's `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` securely in the environment, then run `PYTHONPATH=. python scripts/configure-account.py` (PowerShell: `$env:PYTHONPATH='.'` followed by the Python command). This preserves an existing key rather than silently rotating it.

Auth access/refresh tokens stay encrypted in Redis behind an opaque HttpOnly SameSite cookie. Supabase verifies the account on each protected request, while Postgres RLS and explicit owner filters enforce isolation. This is development-only; production requires HTTPS/Secure cookies and managed Redis/secret storage. No service-role key is used by this slice. Uploaded documents and mailbox integrations remain disabled here.

The user-approved live test used two synthetic Auth accounts, then removed them and their fixtures. To repeat it, obtain explicit account-creation/cleanup consent, run `scripts/prepare-account-test.py --approved`, apply its ignored seed SQL only to the approved development database, run `scripts/check-account.py`, and set `CERTVAULT_LIVE_TESTS=1` for the two browser checks. Keep traces disabled for credential-bearing tests. Apply the matching guarded cleanup SQL and remove temporary credential files afterward. Default CI skips these two tests; it still runs mocked account security tests and all eight local journeys.
