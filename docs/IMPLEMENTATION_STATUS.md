# Implementation status

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

## Checkpoint (2026-11-15)

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
