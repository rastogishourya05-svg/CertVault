# Testing and release gates

## Unit tests
Classifier rules; extraction schema; date parsing; dedupe; size thresholds (below/equal/above); unknown-size bounded stream; approval transitions; notification idempotency; token handling; share expiration.

## Integration tests
Supabase auth + RLS cross-user denial; private storage access; database migrations; Gmail adapter with mocked provider; OAuth callback state; worker retries/backoff; download redirects/SSRF; infected or malformed file quarantine; revoke/disconnect.

## End-to-end Playwright
1. New user onboarding and empty vault.
2. Connect test mailbox in mocked local environment; discover/import sample certificate; observe progress and success notification.
3. Oversized attachment blocked until approval; reject and approve flows.
4. Duplicate import remains single record.
5. Search/filter/preview/edit/download certificate.
6. Generate/edit/copy social draft; no auto-publishing.
7. Opt-in public profile; private certificates remain hidden; share link expiration/revocation.
8. Keyboard-only navigation, screen reader labels, mobile layout, loading/empty/error states.

## Quality gates
`lint`, `typecheck`, Python formatting/lint, pytest, frontend unit tests, Next build, Playwright smoke tests, dependency audit. Save screenshots at 1440px and 390px and inspect them. Never claim live OAuth works based only on mocks. Production launch needs real provider credentials, privacy policy, terms, monitoring and provider approval as applicable.
