# Integration and deployment runbook

## Verified local boundary
Demo files and sessions live under `.local/`; data is synthetic and local storage is not encrypted by this application. Session cookies are HTTP-only, SameSite Strict and loopback-only; HTTPS/Secure cookie handling is required for production. No user can select an arbitrary owner via request parameters. Shares use random capability tokens whose hashes alone are stored, expire, are revocable, and are revoked on trash. Public profiles expose only explicitly selected metadata; downloads stay private.

PDF content is sniffed and parsed with page/text/action bounds, but there is no antivirus, parser sandbox, image validation or OCR. Uploads are demonstration-only and enforce both request-level and observed file-size bounds. Extraction is not authenticity verification. Web links are never fetched. The URL policy helper is preflight only; production must pin resolved IPs for each request and validate every redirect to prevent DNS rebinding.

## External configuration and consent
Do not paste secrets into chats, Git, browser logs or client environment variables. Keep mailbox authorization separate from Supabase sign-in. No external accounts have been accessed by this implementation.

1. Authorize a Supabase **development** project and region; supply its URL and publishable key through secure environment configuration. Service credentials remain backend-only. Implement the production DB/storage adapter, secure session flow (signup/signin/reset/logout), and user-scoped storage access before enabling live mode.
2. Apply `supabase/migrations/20261115103940_certvault_private_vault.sql` only to an authorized development database. Review advisors and test real Auth JWTs, Data API grants, RLS, bucket privacy, signed-link expiry and cross-user denial. SQL stubs do not replace this gate. Worker writes require a narrowly scoped backend role; never expose a service-role key to the browser.
3. Create Google OAuth credentials with exact HTTPS callback URLs and consent/verification for Gmail readonly access. Configure client ID/secret and a versioned Fernet token encryption key server-side. Implement callbacks consuming session-bound one-use state and PKCE, persist encrypted tokens, and perform an explicitly consented test-mailbox import. Gmail history expiry requires a bounded rescan; pagination/cursor updates must commit with jobs, not before them.
4. Configure Microsoft app credentials and Mail.Read/offline_access consent separately. Track Graph deltas per folder. Provider adapters reject unexpected cursor origins before adding bearer credentials. Complete refresh, provider revocation/account-permission removal and disconnect tests before launch.
5. Deploy isolated, resource-limited parsing/scanning workers with an antivirus service and OCR engine. Add full transactional import state transitions, retry scheduling, cancellation, durable cursors, outbox delivery, retention cleanup and global/per-user rate limits. Demo synchronous scans do not provide these production guarantees.
6. Configure an AI vendor only after a user explicitly consents to the precise content sent, retention and purpose. Current captions are deterministic templates, labeled accordingly. No AI calls, direct social publishing or paid-service calls occur. Add schema-validated classification/extraction, confidence/provenance and failure/review handling; never execute instructions from document content.

Provider references: [Google server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server), [Gmail message pagination](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list), [Microsoft auth-code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow), [Graph delta sync](https://learn.microsoft.com/en-us/graph/delta-query-messages), [Supabase JWTs](https://supabase.com/docs/guides/auth/jwts), [Storage RLS](https://supabase.com/docs/guides/storage/security/access-control).

## Local PostgreSQL and worker checks
Start `docker compose -f infra/compose.yaml --profile test up -d postgres-test`. On a fresh disposable database, pipe each file in order into `docker compose -f infra/compose.yaml exec -T postgres-test psql -U postgres -d certvault_test -v ON_ERROR_STOP=1`:

1. `infra/sql/test-bootstrap.sql` (vanilla-Postgres auth/storage stubs, never hosted Supabase).
2. Both SQL files in `supabase/migrations/`, in filename order.
3. `infra/sql/test-rls.sql` (transaction rolled back after assertions).

The bootstrap is intentionally not rerunnable against an existing schema. Use a new disposable database when testing migration changes. Never reset a real user database to make a test pass. `scripts/check-worker.py` creates a temporary synthetic workspace, dispatches a real Redis task, checks persisted imports/notifications, and stops only its own worker process. No task payload carries documents or tokens.

## Release requirements
Production is disabled in API startup. Completing a build does not enable live mode. Before any deployment: wire and verify real persistence/auth/storage/OAuth, finish the missing P0 vault controls (tags/collections/bulk actions/export of documents), complete scanner/link/AI gates above, approve privacy policy/terms/retention/region, and add monitoring, backup/restore tests, secret rotation and audit retention. Review PyMuPDF's AGPL/commercial licensing with the intended distribution model.

Use HTTPS with secure cookies, strict production CSP nonces, explicit CORS origins and no access logging of capability/OAuth URLs. Development CSP permits inline scripts and eval for tooling. The audit removed production unsafe-eval; replace remaining inline allowances with a nonce/hash strategy before launch. CI must pass lint, typecheck, Python/frontend tests, migrations/RLS, production build, dependency/secret audits and E2E with mobile/desktop visual review.

Frontend target is Vercel; API/worker target is a container-capable service with managed Redis/Postgres/private Storage. Infrastructure templates are preparatory. No hosted resource, domain, deployment or paid service may be created without user authorization. Rollback SQL is manual/destructive and deliberately retains storage objects; never run it automatically.

## Development verification update (2026-11-15)
The user-authorized Free-plan project `taeeofpjhubjvypbnldy` is restored and all three CertVault migrations are applied. Hosted SQL ownership/storage-row/column-grant tests passed with disposable records inside a rolled-back transaction. The `/account` development slice subsequently passed actual Auth sign-in/out/refresh and owner-scoped PostgREST preference/certificate tests, plus desktop/mobile browser tests, using two separately approved temporary accounts. Their guarded cleanup completed and no temporary accounts/certificates remain. Direct client Storage upload was denied specifically by RLS; legitimate uploads and signed downloads remain unverified. No external mailbox was accessed.

Existing unrelated tables retain advisor warnings for [anonymous GraphQL schema visibility](https://supabase.com/docs/guides/database/database-linter?lint=0026_pg_graphql_anon_table_exposed). CertVault tables are visible as schema metadata to authenticated users, with owner RLS governing rows; evaluate whether to disable GraphQL before launch ([advisor guidance](https://supabase.com/docs/guides/database/database-linter?lint=0027_pg_graphql_authenticated_table_exposed)). [Leaked password protection](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection) is disabled in the existing project; review availability/configuration without upgrading the Free plan automatically.

## Implementation audit checkpoint
See [IMPLEMENTATION_AUDIT.md](IMPLEMENTATION_AUDIT.md) for the current per-feature classification, actual rerun results, fixed defects and exact external setup. It supersedes historical milestone pass counts when assessing current release readiness. No real mailbox scanning or deployment is enabled.
