# Gmail ingestion development runbook

The pipeline is implemented for **Gmail certificate PDF attachments** behind a disabled-by-default server flag. It is not a verified live Gmail/Supabase Storage integration or production release. No mailbox was accessed and no hosted migration was applied while building it. Existing local demo data is never moved into a real account.

## What runs

`/account` → explicit consent/range/automatic-scan choice → Google OAuth with PKCE, Redis one-use state and browser/session binding → encrypted private token vault → PostgreSQL durable job → Celery → bounded Gmail metadata/history/attachment retrieval → observed size check → ClamAV → networkless/resource-limited Docker PDF parser → private Storage → transactional certificate/file/import/notification/audit rows. The account UI polls activity and refreshes the real vault on stored imports. Private download proxies the object with the user's JWT, reapplying Storage RLS and verifying bytes/hash.

Each invocation processes at most one downloadable file and checkpoints unfinished pages without advancing the mailbox history cursor. Source IDs and owner/SHA-256 constraints dedupe retries. Connection advisory locks serialize workers. A completed page commits its cursor; expired history falls back to the selected backfill range. Beat dispatches durable queued jobs every 30 seconds; opted-in automatic connections become due approximately every five minutes. This is polling, not push/instant delivery. Stop the laptop/worker and scanning stops; queued work remains in PostgreSQL.

Default 50 MiB auto-download threshold comes from account preferences. Known oversized candidates never fetch attachment bytes before approval; unknown/lying sizes are bounded before decoding and storage. Per-file approval permits up to the separate 100 MiB hard cap. Failure never turns off scanning or parsing checks. Reject means no certificate is stored. Disconnect cancels queued jobs and deletes local tokens, attempts Google revocation, and retains existing certificates; the UI reports unconfirmed remote revocation.

## External setup before any live test

1. Keep the approved Google project in **Testing**, add a dedicated test Gmail account, enable Gmail API and retain only `https://www.googleapis.com/auth/gmail.readonly`.
2. In the **Web application** OAuth client, register exactly:
   ```text
   http://127.0.0.1:8000/account/pipeline/gmail/callback
   ```
   This development-only loopback callback is now implemented. It goes directly to FastAPI with `--no-access-log`, avoiding authorization-code URLs in Next.js request logs. Always open the app at `http://127.0.0.1:3000`, not `localhost`; cookies must share the same host. Google's loopback HTTP exception is for development, not production. See [Google redirect rules](https://developers.google.com/identity/protocols/oauth2/web-server#uri-validation).
3. Review/apply `supabase/migrations/20261115133551_certvault_ingestion_pipeline.sql` to the **approved development project only** after authorization for the hosted change. It creates private pipeline tables, owner RLS and a NOLOGIN/NOBYPASSRLS backend role. It does not replace the existing bucket or unrelated tables. Provision a separate backend login that can `SET ROLE certvault_pipeline`; do not use dashboard credentials in application code. Non-loopback PostgreSQL connections require verified TLS. Review the narrow `private.pipeline_due()` scheduler function, which returns only job/owner IDs across accounts.
4. Supply a server-only Supabase Storage credential authorized to upload into the private `certificates` bucket. Prefer a suitable scoped backend identity; a Supabase secret/service key is privileged and must never enter browser code or logs. Positive upload/download and cross-user Storage HTTP tests are still required before calling this integration verified.
5. Securely configure on this laptop (no secret in command arguments or chat):
   ```powershell
   $env:PYTHONPATH='.'
   .venv/Scripts/python scripts/configure-pipeline.py
   ```
   Hidden prompts collect PostgreSQL URL, Storage secret and Google client secret. Client ID is also requested. The script creates ignored `.local/pipeline.json`, generates a separate OAuth encryption key and leaves `live_imports_enabled=false`. Existing configuration/key is never overwritten. Restrict file access to your Windows account; keep the session key in `.local/supabase.json` separate. Never print/upload either file.
6. Configure and verify local security services:
   ```powershell
   docker compose -f infra/compose.yaml --profile ingestion up -d redis clamav
   docker build -f infra/Dockerfile.parser -t certvault-parser:dev .
   ```
   ClamAV initially downloads signatures and can need time to become ready. Port 3310 is loopback-only and unauthenticated: never expose it. Config enforces size/recursion bounds and alerts on scan-limit exhaustion. The parser gets only one read-only PDF, no network, capabilities or secrets, a read-only filesystem, non-root UID, 256 MiB memory, one CPU and a time limit. The worker needs Docker access; never mount the Docker socket into the untrusted parser. Production requires a separately reviewed isolation/deployment arrangement and digest-pinned images.
7. After explicit approval for a bounded test and successful preflight, the developer enables `live_imports_enabled` in ignored config. Restart API/worker. **Do not flip this flag merely to remove the disabled banner.** No real test or activation was authorized/executed during implementation.
8. Start the API with access logging disabled, Next.js, worker and scheduler in separate terminals:
   ```powershell
   .venv/Scripts/python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --no-access-log
   pnpm dev
   .venv/Scripts/python -m celery -A apps.worker.celery_app:celery worker --pool=solo --queues=celery,ingestion --concurrency=1 --loglevel=WARNING
   .venv/Scripts/python -m celery -A apps.worker.celery_app:celery beat --loglevel=WARNING --schedule=.local/celerybeat-schedule
   ```
   Windows solo is for development; Celery process time limits require a supported Linux worker pool for production. Network/scanner/parser operations also have their own bounds. Run one Beat scheduler only. Do not configure HTTP client debug/request logging or trace credential-bearing browser tests.
9. Sign into `/account`, choose **Past 7 days**, leave automatic scans **off**, check consent and connect the dedicated test mailbox. Authorize on Google's site. Click **Scan now** for the first approved test. Verify one synthetic PDF appears, downloads privately and does not duplicate on a second scan. Test oversized approval, rejection, outage recovery and owner denial before opting into automatic scans. Google Testing refresh credentials may expire after seven days; reconnect when necessary.

## Verification and limits

Repeat transactional tests against a disposable migrated local database, never a user database:
```powershell
$env:CERTVAULT_TEST_DATABASE_URL='postgresql://postgres:local-test-only@127.0.0.1:54329/certvault_test'
$env:CERTVAULT_TEST_SECURITY='1' # requires real local ClamAV + built parser
.venv/Scripts/python -m pytest -q
$env:PLAYWRIGHT_CHANNEL='chrome'
pnpm e2e
```
Provider/Storage requests in these tests are explicitly mocked; real ClamAV and Docker parsing can run in the same orchestration. No test result substitutes for actual provider consent and Storage HTTP verification. CI reruns the PostgreSQL suite after all migrations, skipping the security-service smoke unless configured.

Remaining scope: Outlook orchestration, link references/fetching, inline PDFs without attachment IDs, scanned/image OCR, ambiguous-message review/classification and structured metadata are not completed. Detection currently requires a PDF filename and certificate/credential/achievement wording in the subject; it can miss certificates. Filename supplies a review-needed title; issuer/dates are not invented. High-volume history pages over 200 changes require review/backfill improvement. Account signup/reset, full main-dashboard integration, pagination/privacy/deletion/retention and production hardening remain separate release work.

Retries have exponential scheduling and capped attempts, but exhaustive crash/large-file/load testing and provider-specific Retry-After handling remain outstanding. A disconnect/crash between the scanned-object upload and DB commit can leave a private hash-addressed orphan; resuming reuses the same object, but audited orphan-retention cleanup remains to be implemented. Existing files are never silently deleted to compensate. UI notifications are persisted transactionally, not emailed. Production mode still fails closed. Do not represent this milestone as production-ready.
