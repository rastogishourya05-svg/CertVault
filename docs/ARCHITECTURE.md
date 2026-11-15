# Architecture and implementation decisions

## Monorepo
`apps/web` Next.js App Router + TypeScript + Tailwind + shadcn/ui; `apps/api` FastAPI; `apps/worker` Celery worker; `packages` only for genuinely shared schemas/types; `infra` for Docker and deployment.

## Infrastructure
Supabase Auth + Postgres (RLS) + private Storage. FastAPI verifies Supabase JWTs and enforces resource ownership. Redis/Celery runs mail sync, download, OCR, extraction and notifications. Frontend on Vercel; API/worker on container-capable hosting. Keep local Docker Compose for Redis and dependencies. Use migrations (Alembic or SQL migrations, choose one consistently).

## Entities
profiles; email_connections (provider, account, scopes, encrypted tokens reference, sync cursor, state); sync_jobs; candidate_emails (minimal metadata, retention); import_candidates (source, declared_size, observed_size, status, approval); certificates (owner, title, issuer, dates, credential ID, status, source, confidence); certificate_files (private storage path, hash, MIME, bytes); tags; certificate_tags; collections; collection_items; notifications; notification_preferences; share_links (hashed token, expiry, revocation); public_profiles; social_drafts; audit_events. Enforce user ownership, unique dedupe keys, FK constraints, indexes, RLS and migrations.

## State machine
`discovered -> classified -> [awaiting_approval | eligible | needs_review] -> downloading -> quarantined -> scanning -> extracting -> stored -> notified`. Error/retry and rejected states explicit. Make transitions transactional and idempotent. Notification outbox pattern to prevent duplicates.

## OAuth and sync
Separate sign-in OAuth from mailbox scopes. Server-side OAuth callback, CSRF state, encrypted token storage, refresh/revoke. Gmail API first, Microsoft Graph via adapter. Backfill with paginated queries; incremental via provider-supported notifications/delta or scheduled polling. Persist cursor; handle expired history cursors, quota/backoff, disconnect.

## Size and download policy
Default 50 MiB (52,428,800 bytes). Metadata/HEAD size if available, but untrusted. Streaming byte counter with abort before exceeding threshold; temporary quarantine is not a successful download and must be deleted on refusal/failure. Require explicit approval for a specific candidate above threshold, with separate global hard cap and resource limits. Protect from compressed bombs, redirects and oversized decoded payloads.

## AI usage
Rule-based filtering first. Structured classification/extraction with schema validation and confidence/provenance. Send only necessary content with consent and retention policy. LLM must never directly execute arbitrary URLs, shell commands, database writes, or publishing actions. Avoid vector search until a measurable need exists.

## API outline
`/auth/me`, `/connections`, `/connections/{id}/sync`, `/imports`, `/imports/{id}/approve`, `/imports/{id}/reject`, `/certificates`, `/certificates/{id}`, `/certificates/{id}/download`, `/collections`, `/notifications`, `/shares`, `/social-drafts`, `/profile`, `/settings`, `/audit`. Generate OpenAPI and typed frontend client.

## UI direction
Distinctive professional SaaS: deep navy + electric blue/cyan accents, generous whitespace, excellent typography, restrained motion, polished certificate previews, informative dashboards. Avoid generic gradients everywhere and decorative charts with invented data. Responsive sidebar/navigation, onboarding wizard, activity timeline, approval inbox, certificate grid/list, preview drawer, social post editor, profile builder, settings and privacy center.
