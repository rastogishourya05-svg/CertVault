# CertVault Codex operating rules

Read `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, and `docs/TEST_PLAN.md` before implementing features. Follow `.codex/skills/certvault/SKILL.md`.

## Working method
1. Inspect repository and available tools; do not assume credentials or integrations exist.
2. Create a short execution plan in `docs/IMPLEMENTATION_STATUS.md`; implement in vertical slices, not disconnected mockups.
3. For each slice: schema/migration -> backend -> frontend -> tests -> browser verification -> documentation.
4. Run lint, typecheck, unit/integration tests, build, and Playwright. Fix failures before declaring completion.
5. Inspect desktop (1440px) and mobile (390px) screenshots; resolve overflow, inaccessible controls, broken flows and loading/error states.
6. Use real integrations only with configured credentials; otherwise use clearly labeled local mocks and integration tests. Never claim an integration works without testing it.
7. Keep migrations reversible where practical, secrets out of git, and all user documents private by default.
8. Do not automatically publish content, delete user data, or access external accounts without explicit consent.
9. Commit coherent changes with descriptive messages when git is configured; do not overwrite unrelated work.
10. Update status with completed items, test evidence, blockers, and next steps. Do not silently skip requirements.

## Architecture constraints
- Monorepo: `apps/web` Next.js, `apps/api` FastAPI, `apps/worker` Celery; shared Python domain/services package if useful.
- Supabase Auth, PostgreSQL with RLS, private Supabase Storage; use server-side authorization on every access.
- Redis/Celery for background imports; jobs must be idempotent, retryable, observable, and rate-limited.
- Deterministic code for downloads, policy checks, security and storage. Use AI only for classification, ambiguous extraction, categorization and drafting.
- Never expose OAuth access/refresh tokens, API keys or document contents to client logs or LLM calls without explicit policy and consent.
- Do not introduce microservices, LangGraph, Kubernetes, vector DB, or extra MCP servers unless a demonstrated requirement justifies them.

## Definition of done
A feature is done only when it works end-to-end, has tests, proper authorization, accessible responsive UI, empty/loading/error states, and has been verified in a real browser. Never invent test results.

## Current development checkpoint
- Runtime currently supports an explicit local demonstration only; preserve loopback restrictions, synthetic-data labels and fail-closed live mode until production gates pass.
- Use `pnpm` scripts for the web app and `.venv/Scripts/python` on Windows. `pnpm build` uses Webpack because this machine's Turbopack CSS worker fails in production builds.
- Run API with `--no-access-log` to avoid logging capability URLs. Never put share tokens in analytics or operational logs.
- Docker services live in `infra/compose.yaml`; the `test` profile is a disposable PostgreSQL database with explicit Supabase-compatible stubs. Passing these tests does not establish hosted Supabase integration.
- Read `docs/IMPLEMENTATION_STATUS.md` for verified evidence and remaining work before resuming. Do not silently enable real integrations or replace synthetic adapters with untested live claims.
