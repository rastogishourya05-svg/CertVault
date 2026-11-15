# Implementation status

## Gmail pipeline checkpoint (2026-11-15)
Development Gmail PDF-attachment automation is implemented; **live imports remain disabled and are not production-ready**. Exact activation/configuration and remaining limits: [GMAIL_PIPELINE.md](GMAIL_PIPELINE.md).

- Added session/browser-bound one-use OAuth callback + PKCE, encrypted private token vault, scope/range/automatic-scan consent, refresh/revocation, owner RLS backend role, durable job dispatch/retries/page checkpoints/history fallback, source/hash dedupe, per-file approval/rejection and observed-byte bounds.
- Added real ClamAV integration and networkless, non-root, read-only Docker PDF processing with resource/time limits; only scanned/validated PDFs reach the Storage adapter. Certificate/file/import/notification/audit writes commit transactionally. Authorized private downloads reapply user JWT Storage RLS and verify length/hash. `/account` now has availability, connection, scan, activity, approvals, notifications and download controls. Main demo remains separate.
- Evidence: **67 pytest passed** with disposable PostgreSQL and synthetic provider/Storage mocks, including one complete orchestration with real ClamAV + Docker parser. All four migrations and RLS assertions passed on a fresh disposable PostgreSQL container (65 tests at that fresh-schema checkpoint; two subsequent dispatcher/download regressions also pass in the final 67-test suite). Real Redis/Celery sample smoke passed. Clean synthetic PDF accepted and harmless in-memory EICAR signature rejected by real ClamAV. Python lint/format, OpenAPI drift, frontend lint/typecheck/build, 2 Vitest tests, Python/full frontend dependency audits passed. Upstream TestClient/Node deprecations remain.
- Browser evidence: final full Playwright run **12 passed, 2 skipped** (8 local demo + 4 mocked account/automation desktop/mobile journeys; real Auth fixtures absent) because temporary fixtures were removed. Initial browser launch failed because bundled Chromium was absent; rerun used installed Chrome successfully. Playwright MCP inspected 1440px/390px synthetic account screenshots, consent gating and no horizontal overflow/JS errors. No new real Auth account, Gmail request, hosted schema change or Storage object was created.
- External blockers: user confirmed **neither credential set is ready**; ignored pipeline config is absent; need Google Web OAuth client ID/secret, dedicated test mailbox, backend PostgreSQL login with `certvault_pipeline` role, server-only Storage credential, and reviewed hosted migration application. Callback now exists at `http://127.0.0.1:8000/account/pipeline/gmail/callback`; register exactly this loopback URI. `scripts/configure-pipeline.py` accepts hidden secret inputs, generates its own OAuth key, and preserves the disabled live flag. Do not paste secrets into chat.
- Remaining independent work: Outlook orchestration, links/inline PDFs, OCR/structured extraction/review, audited orphan cleanup, exhaustive crash/load/large-file/provider quota tests, full main-vault integration and prior release/security/privacy lifecycle gaps. High-volume history and provider-specific Retry-After need further handling. No production readiness or live integration is claimed.

Next action: securely configure the server credentials; review/apply the pipeline migration only to the approved development project, verify real Storage ownership, then obtain explicit consent for one bounded synthetic-mailbox Gmail test. Keep automatic scans off for that first test. No deployment or paid resources were enabled.

Local ClamAV was stopped after verification to free laptop memory; its image/signature volume and parser image are retained. Redis and the development UI/API remain available. Restart the scanner using the runbook before security-service tests or any approved import.

## Historical pre-pipeline audit (2026-11-15)
**Not production-ready.** Detailed feature-by-feature classification and exact setup: [IMPLEMENTATION_AUDIT.md](IMPLEMENTATION_AUDIT.md).

- The main UI uses real FastAPI requests and durable SQLite/local files, but its mailbox, approvals, notifications, sharing and caption flows are **demo/mock only**. `/account` is a separate, incomplete Supabase Auth/Postgres slice; there is no unified production vault or working cloud certificate upload/download pipeline.
- Current checks: **53 pytest passed**, **2 Vitest passed**, Python lint/format, frontend lint/typecheck, OpenAPI drift, build and full dependency audits passed. **8 local Playwright journeys passed + 2 new mocked-account UI journeys passed; 2 live Auth journeys skipped** because their temporary accounts were removed. Prior milestone live Auth tests remain historical evidence, not a new audit pass.
- Current real Redis/Celery smoke and transactional local PostgreSQL RLS assertions passed. Hosted read-only checks confirm 18 CertVault RLS tables, a private bucket and token client-deny policy. No hosted rows, migrations or account settings were changed.
- Playwright MCP inspected 1440px/390px screenshots, reload/disk persistence, document-only search, oversized rejection, mobile navigation/dialog/Escape and injected API failure/recovery. No horizontal overflow. No real scans, deployment, emails, AI calls or new external test accounts.
- Fixed: backend document-text/tag search wiring; metadata-clobbering favorite requests; misleading Auth/data errors and Redis cleanup exception; account loading/search races and unsaved preference overwrite; smoke-test queue isolation; live-test trace privacy; new misleading sample log wording; favicon; clipped category label; production CSP `unsafe-eval` removal. Nonce/inline CSP work remains.

### Priority and blockers
1. **P0:** unify Supabase authentication/persistence with the main vault; implement signup/confirmation/reset, full owner-scoped operations, pagination and cloud audit. These are missing code, not just missing keys.
2. **P0:** quarantine + antivirus + parser isolation/OCR/resource bounds; complete scanned-object Storage upload and authorized download/signing; test cross-user positive/negative Storage HTTP paths.
3. **P0:** API-to-Celery dispatch, durable state machine/cursors/retries/quotas/cancellation, transactional notifications outbox and recovery tests.
4. **P0:** Gmail then Graph OAuth callback/consent/token-vault/revocation and incremental sync. Credentials are absent (`GOOGLE_CLIENT_*`, `MICROSOFT_CLIENT_*`, `OAUTH_TOKEN_ENCRYPTION_KEY`) and callbacks are not implemented. Do not enable real scanning.
5. Complete production preview/export/deletion/retention/review/preferences/accessibility, then P1 hosted sharing/profiles/QR/manual social features and consented AI.
6. External setup: server-only ingestion DB/Storage permissions and credential, Auth SMTP/verified sender/Site URL/callback allowlist, consented provider test mailboxes and OAuth registrations, production Redis/worker/scanner/OCR hosting, optional AI/notification provider credentials and budgets. Exact setup and official links are in the audit; adding keys alone will not finish the app.
7. Before launch: HTTPS/Secure cookies, production origin/CSRF/CSP nonce controls, secret rotation, legal/retention/region/license decisions, executed CI, monitoring/backups/restore tests and provider approvals. Existing unrelated Supabase tables/policies remain untouched.

Next work should implement the secure authenticated manual-ingestion slice with mocks and disabled live mailbox features. No deployment or paid-service activation is authorized.

## Plan (2026-11-15)
All specifications and starter instructions reviewed. Started from specification-only repository. Dedicated project Git repository now initialized (user's original initialization was in the home directory).

1. Foundation: workspace, local environment, design system, validated API, private schema.
2. Private vault: demo session, manual PDF ingestion, metadata review, dedupe, search, favorites, download, trash/recovery and notifications.
3. Ingestion: consented sample mailbox, idempotent discovery, bounded size policy, approval/rejection, audit; Celery/Redis boundary.
4. Production integrations: Supabase auth/RLS/storage, Gmail then Graph OAuth/sync, malware scanning/OCR. Enable only with verified credentials and infrastructure.
5. Sharing/profile/posts: expiring/revocable shares, explicit profile opt-in, editable drafts; AI needs content consent and configured provider.
6. Release gates: lint/typecheck/unit/API/build/E2E, desktop/mobile inspection, security review and deployment runbook. No production deployment.

## Decisions and missing specifications
- Local demonstration is loopback-only, explicitly labeled, synthetic mailbox + SQLite/private local files. Do not use real documents or expose to a network. Production must fail closed.
- Versioned PostgreSQL SQL migrations; separate SQLite schema for local tests. Live Supabase RLS is a release gate.
- Initial hard cap 100 MiB, auto threshold 50 MiB. Production region, retention, legal text, allowed link providers, notification vendor and AI vendor need release decisions.
- Malware scanning and isolated parsing are required before real untrusted file ingestion. Link fetching stays disabled until DNS-pinned SSRF protection is verified.
- Initial inspection found Node/Python/pnpm but no credentials or Docker. Docker and dedicated Git are now configured; Supabase development access was later explicitly authorized (below).

## Historical completed-milestone evidence (2026-11-15)

### Implemented and verified
- Local workspace: explicit synthetic onboarding, Gmail/Outlook sample consent and discovery, idempotent imports, 50 MiB approval policy / 100 MiB hard cap, approve/reject, PDF upload/text extraction, hash dedupe, metadata editing, search/filter/favorites, tags, private collections, atomic bulk favorite/trash/restore, PDF download, notifications/audit, JSON metadata export, expiring/revocable shares, opt-in profiles, editable template captions and dark mode. No AI calls or social publishing.
- Responsive Next.js/TypeScript/Tailwind/Radix-shadcn components and navy/blue/cyan design system. Generated OpenAPI/TypeScript models and drift check. E2E starts/waits for dev services automatically.
- Isolated, mock-tested Gmail/Graph adapters, PKCE/state replay/expiry protection, encrypted token primitive, refresh and Supabase JWKS verifier. Live mailboxes are not wired.
- 49 pytest tests passed; 2 Vitest tests passed; frontend lint/typecheck and Python lint/format passed; Webpack production build passed. Final full Playwright run: 10 passed (8 local journeys plus 2 real Supabase account journeys) across desktop/mobile. Latest 1440px/390px screenshots inspected; no horizontal overflow. CI workflow prepared but not run remotely.
- All frontend dependencies (including dev) audit clean after Vitest update and scoped minimatch override. Python runtime requirements audit clean. Starlette TestClient currently emits an upstream httpx deprecation warning; tests pass.

### Supabase development project
- User explicitly approved inspection, selected `supabase-lime-car` (`taeeofpjhubjvypbnldy`, us-east-1), and approved restoration on the existing Free plan. Project is ACTIVE_HEALTHY; no paid changes or deployment.
- Inspected existing schema and preserved unrelated users/trips/aqi_logs/rewards/user_rewards tables.
- Applied migrations `20261115103940_certvault_private_vault.sql`, `20261115105405_certvault_ownership_hardening.sql` and `20261115111339_certvault_account_profile_bootstrap.sql`; local filenames match hosted migration history.
- Actual hosted SQL tests passed for ownership, cross-user read/update/insert denial, storage row ownership, column grants and direct-share consent boundary. Synthetic test rows were rolled back; zero test profiles retained. 18 CertVault tables have RLS, certificate bucket is private, OAuth token table denies client roles.
- `/account` now verifies real Supabase password sign-in/out, opaque HttpOnly sessions, server-side Fernet-encrypted Redis tokens, refresh serialization, online user validation, private certificate search/favorites and profile preferences through RLS. No service-role key is used. Production remains disabled and both runtimes remain loopback-only.
- User explicitly approved two temporary synthetic Auth accounts and cleanup. Real HTTP tests passed for both accounts: sign-in, encrypted session storage, cross-user isolation, profile writes, refresh, direct Storage upload RLS denial, sign-out and cookie replay denial. Desktop/mobile browser tests passed with traces disabled; screenshots reviewed.
- Removed both temporary accounts, associated metadata and ignored credential/seed/cleanup files. Verified 0 temporary Auth accounts, 0 temporary certificates, and 0 objects in the private bucket. Ignored development configuration/encryption key retained; no secrets in Git.
- Registration/password recovery, legitimate Storage uploads/signed downloads and real mailbox imports remain unverified/incomplete. A private bucket and a denied upload are not claims of a working ingestion integration.
- Existing project advisor warnings (GraphQL schema discoverability and password leak protection) require review before launch; unrelated application grants remain untouched. See OPERATIONS.md.

### Saved checkpoint and next action
- Local Docker engine stopped during pause. Restarted Docker Desktop and brought Redis/Postgres back healthy; final local hardening/RLS and real Redis/Celery rerun passed (3 stored certificates, 1 approval, 4 notifications).
- Foundation committed as `d1b64a1`; account slice is ready for its checkpoint commit. User requested saving here because Gmail OAuth and scoped backend Storage credentials are not yet available. No further integration activation is authorized by silence.
- Next resume action: securely configure the missing external credentials, then implement safe ingestion/storage and mailbox callbacks as the next tested vertical slice. Preserve all existing Supabase tables and fail-closed production mode.
- Remaining: registration/password recovery, full vault/Storage HTTP wiring, OAuth callbacks/durable sync, scanner isolation/OCR, allowlisted DNS-pinned links, cloud audit/outbox/retention/notification preferences, full-document export, AI consent/provider, legal/license review and deployment hardening. P2 not started. No production deployment or paid upgrade occurred.
