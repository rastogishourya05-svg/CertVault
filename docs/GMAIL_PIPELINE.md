# Gmail ingestion development runbook

### Local image and issuer-file imports

Send a synthetic PDF, PNG or JPEG attachment to the dedicated mailbox. Put certificate, credential or achievement in its subject or filename. In the signed-in dashboard choose **Connected mailboxes → Scan now**, then open **Activity**. Repeated scans of the same source reuse its decision. Identical bytes already stored for that owner skip parsing and upload.

For link-only mail, the supported direct-file host is `udemy-certificate.s3.amazonaws.com` with a `/pdf/UC-….pdf` or `/image/UC-….jpg` path. Use **Approval inbox** to authorize the download. Other relevant issuer URLs require manual review. Redirects, signed query strings, nonpublic IP addresses, missing content length and files above 50,000,000 bytes are rejected. OCR and editable metadata describe the document. Issuer verification requires separate evidence.

**My vault** supports field review, category correction, selected-file operations and private ZIP export. The archive contains active originals and a JSON manifest. Use **Trash** to restore files. For a forgotten local account password, choose **Forgot your password?** and follow the link-copy instructions for the local test inbox. Successful recovery invalidates existing app sessions.

### Signed-in local dashboard

Open `http://127.0.0.1:3000/account`. Use **Connected mailboxes** to start a manual scan and **Activity** to see its results. Completed runs created with migration `20261119070000` record outcomes per unique attachment, including files previously stored. A newly saved file links to its owner-authorized preview. Older scans retain their recorded status. Activity shows the latest 20 runs and 100 recent import items. The approval inbox queries pending decisions separately.

Use **My vault** for previews, downloads, source/search filters, favorites, and grid/list views. **Collections & tags** stores private memberships in the existing RLS tables. **Preferences** supports download thresholds specified in fractional MiB, rounded to bytes. The server enforces the configured hard limit.

For a local regression with real Auth and private Storage, start the local app and security services, set `$env:PYTHONPATH='.'`, then run `.venv/Scripts/python scripts/check-account-dashboard.py --browser`. The check creates two synthetic local accounts, uploads and downloads test PDFs, verifies isolation and duplicate handling, exercises Chrome at two sizes, then removes its own fixtures. It never triggers a mailbox scan. The cleanup uses the local Storage container's existing internal credential solely inside that container to remove the generated object paths.


## Hackathon MVP local setup — current instructions

This section supersedes the older hosted-project setup below for the hackathon MVP. **Do not connect CertVault to project `taeeofpjhubjvypbnldy` (the dashboard labels it PRODUCTION), run `db push`, apply hosted migrations, or use its database credentials.** The MVP uses the local Supabase CLI stack at `http://127.0.0.1:54321` and a disposable local PostgreSQL test database. No service-role/project-secret Storage key is used. Live Gmail imports remain off until explicitly enabled from the local configuration prompt.

### Configure local Auth and pipeline credentials

1. Start local Supabase from the repository root and confirm the status target says local/`127.0.0.1:54322`:
   ```powershell
   npx.cmd supabase start
   npx.cmd supabase status
   ```
   The status output contains local API keys and the local database password. Keep it in your terminal; do not paste it in chat or save it in the repository.
2. Configure the local account using the anon/publishable key from that local status output. The prompt is hidden; the config is written outside the repo:
   ```powershell
   $env:PYTHONPATH='.'
   .venv/Scripts/python scripts/configure-account.py
   ```
3. Ensure the Google **Web application** OAuth client has this exact redirect URI and remains in Testing with only the dedicated Gmail test user allowlisted:
   ```text
   http://127.0.0.1:8000/account/pipeline/gmail/callback
   ```
   Before configuring the pipeline, provision the local restricted DB login in Supabase's local PostgreSQL container:
   ```powershell
   docker exec -it supabase_db_CertVault psql -U supabase_admin -d postgres
   ```
   At the `psql` prompt create the no-admin login and grant only SET membership, then set its password using psql's hidden prompt:
   ```sql
   CREATE ROLE certvault_ingest LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
   GRANT certvault_pipeline TO certvault_ingest WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;
   \password certvault_ingest
   ```
   `\password` asks for the password twice without echoing it. Do not put a password in SQL. The app connects as `certvault_ingest`, then executes `SET ROLE certvault_pipeline` for each pipeline transaction.

   Configure the local pipeline. Enter the Web client ID, client secret, and **local `certvault_ingest` database password** only at hidden terminal prompts:
   ```powershell
   .venv/Scripts/python scripts/configure-pipeline.py
   ```
   The script creates a new Fernet key and stores settings under `%LOCALAPPDATA%\CertVault\pipeline.json`. At the final prompt, press Enter to keep Gmail imports disabled. Only type `ENABLE MANUAL GMAIL IMPORTS` when you are ready to authorize this dedicated mailbox and manually scan the synthetic message. Automatic scans are rejected in code.

   If pipeline credentials were already configured with the local `postgres` login, preserve the existing OAuth credentials and activation setting, set the restricted role password as above, then run this updater to verify `session_user = certvault_ingest` and `current_user = certvault_pipeline` before atomically changing only the saved database URL:
   ```powershell
   $env:PYTHONPATH='.'
   .venv/Scripts/python scripts/update-pipeline-db-user.py
   ```
4. Start the local supporting services and worker (no Celery Beat/scheduler):
   ```powershell
   docker compose -f infra/compose.yaml --profile ingestion up -d redis clamav
   .venv/Scripts/python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --no-access-log
   .venv/Scripts/python -m celery -A apps.worker.celery_app:celery worker --pool=solo --queues=ingestion --concurrency=1 --loglevel=WARNING
   pnpm dev
   ```
   Keep local Supabase, Redis, ClamAV, API, worker, and Next.js on loopback. Do not open service ports to the LAN. ClamAV must report healthy before uploading or scanning.
5. Open `http://127.0.0.1:3000/account`, create/sign into a local CertVault account, connect the dedicated test Gmail address with the read-only consent checkbox, then click **Scan now** yourself. Use a PDF attachment and a subject containing `certificate`, `credential`, or `achievement`; unsupported/ambiguous messages can be missed. Confirm the imported certificate appears once, can be viewed/downloaded, and a second manual scan marks it duplicate. Do not infer success from the UI until a real test completes.

If the local Account config or pipeline config already exists, the setup scripts intentionally refuse to overwrite it. Preserve the existing file and ask for help to rotate/update it safely; never delete it just to make setup rerun.

### Current verification boundary

The local upload-ticket migration and RLS policy have been applied and transactionally tested on local Supabase; the full API pipeline has passed against synthetic PostgreSQL, mocked Gmail/Storage, real local ClamAV and the isolated parser. Browser journeys passed with mocked APIs. **The OAuth secrets have not yet been entered, the real test mailbox has not been connected/scanned, and an actual local Supabase Storage upload/download has not been verified.** Treat a real integration as unverified until the manual test above succeeds. Do not follow the historical hosted database/login/`sb_secret_` instructions below for this MVP.

**Historical note:** an earlier pipeline milestone applied a hosted migration, with user authorization at that time, to project `taeeofpjhubjvypbnldy` / primary `main` (dashboard label `PRODUCTION`). That project is outside the current MVP target and must not be used or modified for this demo. The code is still not a verified live Gmail/Storage integration or production release; no mailbox has been scanned by the implementation agent. Existing local demo data is never moved into a real account.

## Current MVP behavior

Scanned PDF support: the isolated parser now tries English OCR when a page has fewer than 30 extracted characters (150 DPI, maximum 3 OCR pages). Existing malware checks, active-action/embedded-file rejection and container limits remain enforced. XML metadata is not interpreted and does not by itself reject a PDF. Standalone PNG and JPEG certificates now use English OCR in the same parser, with a 12-million-pixel input limit. OCR and parsing extract information; they do not verify issuer authenticity. A manual rescan retries prior parser-review candidates; identical stored owner hashes avoid redundant parsing/upload.

Manual scan recovery: each new explicit Scan now job revisits the connected account's date range, even when a previous scan completed with no candidates. PDFs are listed within that range; certificate, credential or achievement wording may appear in the subject or attachment filename. Source IDs and content hashes prevent repeated storage. Images remain unsupported. The UI explains an empty completed scan and links back to the private vault.

`/account` → explicit Gmail read consent and scan range → Google OAuth with PKCE, Redis one-use state and browser/session binding → encrypted private token vault → PostgreSQL durable job created only when the user clicks **Scan now** → Celery → bounded Gmail metadata/history/attachment retrieval → observed size check → ClamAV → networkless/resource-limited Docker PDF parser → private Storage → transactional certificate/file/import/notification/audit rows. The account UI polls activity and refreshes the real vault on stored imports. Private download proxies the object with the user's JWT, reapplying Storage RLS and verifying bytes/hash.

Each invocation processes at most one downloadable file and checkpoints unfinished pages without advancing the mailbox history cursor. Source IDs and owner/SHA-256 constraints dedupe retries. Connection advisory locks serialize workers. A completed page commits its cursor; expired history falls back to the selected backfill range. **The hackathon MVP has no Celery Beat, scheduler, or automatic scan option.** Stop the laptop/worker and scanning stops; queued work remains in local PostgreSQL.

Default 50 MiB auto-download threshold comes from account preferences and remains configurable in MiB. Real Supabase ingestion also enforces a separate **50,000,000-byte (50 MB decimal)** hard ceiling, compatible with the verified Supabase Free global upload cap. A known candidate above this limit is rejected before fetching attachment content; approval only applies to files above the user's threshold that remain at or below the hard ceiling. Unknown/lying sizes are bounded during retrieval and rechecked before upload. A Storage `413` or recognized size-limit rejection is terminal, marks the import rejected, and produces a clear notification instead of retrying. The local synthetic demo remains separately capped at 100 MiB and does not imply that Supabase accepts files that large. Failure never turns off scanning or parsing checks. Reject means no certificate is stored. Disconnect cancels queued jobs and deletes local tokens, attempts Google revocation, and retains existing certificates; the UI reports unconfirmed remote revocation.

## Manual backup and recovery gate

The approved Free-plan project is `taeeofpjhubjvypbnldy`, primary `main` (dashboard labels it `PRODUCTION`); no isolated hosted branch exists. The read-only inventory on 2026-11-15 found **2 Auth users, 2 identities, 1 profile, 1 private `certificates` bucket, and 0 Storage objects**. It also found only transient Auth records: 1 session, 1 refresh token, 2 flow states, 1 MFA AMR claim and 1 one-time token. Email connections, jobs, certificates, certificate-file rows, notifications and audit events are empty. `vault` has no data; `realtime` contains only 96 migration-history rows. Only table names and counts were read; no user row contents were exported. Preserve durable users/identities and application data; omit sessions, refresh tokens, flow state, one-time tokens and session AMR claims so all users must reauthenticate after a restore. Bucket/object metadata is in PostgreSQL; current Storage bodies are empty, so there are no object bytes to copy today.

Docker Desktop Engine 29.9.3 is reachable from an authorized Docker shell. The official `postgres:17-alpine` image supplied PostgreSQL client tools at 17.12 and was used for synthetic and hosted dump/restore work. Its system CA bundle alone did not trust this project's database certificate; the Supabase database CA was downloaded from Project Settings → Database → SSL Configuration and saved as `%LOCALAPPDATA%\CertVault\backups\taeeofpjhubjvypbnldy\supabase-ca.crt`. The standalone Supabase CLI v2.122.1 archive was hash-checked but blocked by Windows Application Control; the official npm CLI package v3.1.0 ran through `npx.cmd`. Do not bypass Windows security policy. A read-only hosted permission check found `postgres` is non-superuser with `BYPASSRLS`, `SELECT` on all 69 relations and required `SELECT`/`USAGE` on all three sequences across non-system schemas; zero large objects exist. The protected destination is outside the repository at `%LOCALAPPDATA%\CertVault\backups\taeeofpjhubjvypbnldy`; its ACL grants Full Control only to the current Windows user and SYSTEM. `scripts/backup_crypto.py` packages staging files into a streaming AES-256-GCM bundle and prompts for its passphrase locally without echoing it.

On 2026-11-16, a read-only `pg_dump` of approved project `taeeofpjhubjvypbnldy` / `main` completed with exit code 0 (473,387-byte archive); `pg_restore --list` exited 0 (65,347-byte listing). The encrypted `.cvault` bundle was authenticated and extracted locally, and its dump SHA-256 matched the manifest. An isolated restore into a new `certvault_restore` database in a fresh Supabase local stack then passed with `pg_restore` exit code 0. Aggregate counts matched the hosted inventory (2 Auth users, 2 identities, 1 profile, 1 private bucket, 0 Storage objects, and zero application certificates/imports/notifications/audit rows); excluded Auth session/token rows were zero. RLS was enabled on all 34 restored public/private/storage tables, with 31 policies; migration counts were 3 Supabase migrations and 96 Realtime migrations. No row contents were displayed. After verification and user approval, the local stack's three labeled Docker volumes and plaintext staging/verification directories were removed. The encrypted bundle and CA certificate remain outside the repository.

### Create the hosted backup locally

This step requires the approved project's database password. **Do not send it to Codex or place it in a URI, command literal, environment variable, log or file.** If the password is unavailable, stop; do not reset it without a separate decision, since that may disrupt existing database clients. Open PowerShell on this laptop and use the dashboard's **Connect → Session pooler** host, port and exact username (`postgres.<project-ref>` format when shown). The following passes only non-secret connection details as arguments and lets `pg_dump -W` prompt for the password in the terminal:

```powershell
Set-Location 'C:\Users\shour\OneDrive\Desktop\CertVault'
$backupRoot = Join-Path $env:LOCALAPPDATA 'CertVault\backups\taeeofpjhubjvypbnldy'
$caPath = Join-Path $backupRoot 'supabase-ca.crt'
if (-not (Test-Path -LiteralPath $caPath -PathType Leaf)) { throw 'Download the Supabase database CA certificate to supabase-ca.crt in the protected backup directory first.' }
$stage = Join-Path $backupRoot ("staging-{0}" -f (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'))
New-Item -ItemType Directory -Path $stage -ErrorAction Stop | Out-Null
$poolerHost = (Read-Host 'Session pooler host from Supabase Connect').Trim()
if ($poolerHost -notmatch '^[a-z0-9-]+\.pooler\.supabase\.com$') { throw 'Enter only the Session pooler host for the approved Supabase project.' }
$poolerUser = (Read-Host 'Session pooler username from Supabase Connect').Trim()
if ($poolerUser -ne 'postgres.taeeofpjhubjvypbnldy') { throw 'Username does not target the approved project taeeofpjhubjvypbnldy.' }
$poolerPort = 5432
$dumpPath = Join-Path $stage 'full-project.dump'
if (Test-Path -LiteralPath $dumpPath) { throw 'Dump path already exists; preserve it and choose a fresh staging folder.' }
docker run --rm -it -e PGSSLMODE=verify-full -e PGSSLROOTCERT=/certs/supabase-ca.crt -v "${stage}:/backup" -v "${backupRoot}:/certs:ro" postgres:17-alpine `
  pg_dump --host $poolerHost --port $poolerPort --username $poolerUser --dbname postgres `
  --format=custom --password `
  --exclude-table-data=auth.sessions --exclude-table-data=auth.refresh_tokens `
  --exclude-table-data=auth.flow_state --exclude-table-data=auth.one_time_tokens `
  --exclude-table-data=auth.mfa_amr_claims --file=/backup/full-project.dump
```

Use the exact Session Pooler host from the dashboard and port 5432. `PGSSLMODE=verify-full` verifies TLS chain and hostname; `PGSSLROOTCERT` points at the downloaded project database CA certificate mounted read-only into the container. Do not weaken TLS to `require` or disable verification to get past a certificate error. The command intentionally keeps object ownership and ACLs in the recovery archive; the restore target must provide the matching Supabase roles. `pg_dump` does not save global role definitions or passwords. With no `--schema` filters it includes all non-system schemas, including application, `auth`, `storage`, `extensions`, `realtime`, `supabase_migrations` and `vault`; the only data exclusions are the listed transient Auth tables. Database dumps do **not** contain Storage object bodies. Before treating the dump as complete, verify its target from the dashboard, run `pg_restore --list`, capture a non-sensitive manifest (project ref, branch, UTC time, `pg_dump --version`, SHA-256, excluded transient Auth tables, and the inventory counts above), and compare object counts. Do not print or inspect Auth row contents.

Write the archive listing and manifest into the protected staging directory without displaying them:

```powershell
$pgVersion = docker run --rm postgres:17-alpine pg_dump --version
docker run --rm -v "${stage}:/backup:ro" postgres:17-alpine `
  pg_restore --list /backup/full-project.dump | Set-Content -Path (Join-Path $stage 'restore-list.txt')
$dumpHash = (Get-FileHash (Join-Path $stage 'full-project.dump') -Algorithm SHA256).Hash.ToLower()
[pscustomobject]@{
  project_ref = 'taeeofpjhubjvypbnldy'; branch = 'main'
  captured_at_utc = (Get-Date).ToUniversalTime().ToString('o')
  pg_dump = $pgVersion; dump_sha256 = $dumpHash
  auth_users = 2; auth_identities = 2; storage_buckets = 1; storage_objects = 0
  excluded_transient_auth = @('sessions','refresh_tokens','flow_state','one_time_tokens','mfa_amr_claims')
} | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $stage 'manifest.json') -Encoding utf8
```

Encrypt the staged dump into a new `.cvault` file. The script refuses overwrites; remember the 16+ character passphrase in an approved password manager because it cannot be recovered:

```powershell
$encrypted = Join-Path $backupRoot ("certvault-{0}.cvault" -f (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'))
.venv/Scripts/python scripts/backup_crypto.py encrypt --source $stage --output $encrypted
```

The encryption helper is unit-tested for round-trip, tampering/wrong passphrases and unsafe archive paths. Keep plaintext staging within the user/SYSTEM-only ACL and remove it after the isolated restore rehearsal and encrypted artifact verification are complete. For the 2026-11-16 backup, that rehearsal passed; the user approved removal of all plaintext staging/verification folders and the three Docker volumes for the disposable restore stack. The encrypted `.cvault` artifact and CA certificates were preserved. The user verified C: is 100% encrypted with BitLocker and Protection On; the final `.cvault` artifact is separately AES-GCM encrypted.

### Restore rehearsal and Storage objects

Restore only from the authenticated decrypted bundle into a fresh, disposable local Supabase-compatible database. Never use the hosted connection string as a restore target or restore this managed-schema archive into the existing vanilla PostgreSQL test database. Use a fresh local stack in a separate workspace (not the CertVault repository, whose migrations are applied on start), and verify all published ports are loopback-only before loading data. On this Windows machine, Docker Desktop's **Local-only port binding** setting was required; the custom bridge `host_binding_ipv4` option alone still showed wildcard bindings. The restore went into a new `certvault_restore` database, leaving the stack's default database untouched.

For a new empty target, **do not pass `--clean`**: it caused a missing `storage` schema error before the target had objects; the transaction rolled back. Restore succeeded without it using a single transaction and `--no-owner --no-privileges`. The local stack's `postgres` role could not set `log_min_messages`; use local `supabase_admin` only for this disposable restore. The temporary dump copy inside the database container was hash-checked and removed afterward. Verify Auth/application/Storage aggregate counts, RLS flags and policy totals, and migration history without selecting row contents. This project's 2026-11-16 rehearsal passed those checks; after user approval, its stopped stack containers and specifically labeled Docker volumes were removed, as were plaintext staging/verification directories. The encrypted archive remains outside the repository.

If a later inventory shows Storage objects, fetch each private object server-side using authorized credentials, verify its byte count and SHA-256 against `storage.objects` metadata, include its opaque path and bytes in the encrypted bundle, and verify all hashes after restore. Never create public URLs or log signed URLs/tokens. Current object count is zero, so no Storage object credential is needed for this backup pass.

## Historical hosted-pipeline configuration (reference only; do not follow for the MVP)

The following steps document an earlier hosted integration design and are not the setup for the current demo. Follow only “Hackathon MVP local setup” above. In particular, do not connect to the production-labeled project, enter its database URL, create a hosted role, use project-wide Storage keys, start Celery Beat, or run `db push`.

1. Keep the approved Google project in **Testing**, add a dedicated test Gmail account, enable Gmail API and retain only `https://www.googleapis.com/auth/gmail.readonly`.
2. In the **Web application** OAuth client, register exactly:
   ```text
   http://127.0.0.1:8000/account/pipeline/gmail/callback
   ```
   This development-only loopback callback is now implemented. It goes directly to FastAPI with `--no-access-log`, avoiding authorization-code URLs in Next.js request logs. Always open the app at `http://127.0.0.1:3000`, not `localhost`; cookies must share the same host. Google's loopback HTTP exception is for development, not production. See [Google redirect rules](https://developers.google.com/identity/protocols/oauth2/web-server#uri-validation).
3. **Completed 2026-11-16:** with user authorization, applied `supabase/migrations/20261115133551_certvault_ingestion_pipeline.sql` to project `taeeofpjhubjvypbnldy` / primary `main` (dashboard label `PRODUCTION`). Post-apply checks confirmed three private tables with forced RLS and owner policies, a safe `NOLOGIN` pipeline role, and the scheduler function. The migration did not create the login or set a password; it made no changes to unrelated application tables or Storage settings.
4. **Completed 2026-11-16:** the user created the dedicated login without putting a password in SQL:
   ```sql
   CREATE ROLE certvault_ingest LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
   GRANT certvault_pipeline TO certvault_ingest WITH SET TRUE;
   ```
   In a trusted local `psql` session, the user verified `session_user = certvault_ingest`, and `SET ROLE certvault_pipeline` succeeded; `RESET ROLE` returned to `certvault_ingest`. The password was entered locally and not shared. Do not use the dashboard `postgres` role in the application. For the app URL, use the **Session pooler** details from this project and username `certvault_ingest.<project-ref>` on port 5432. The backend explicitly verifies TLS certificates and hostnames for non-loopback database hosts. Review the narrow `private.pipeline_due()` scheduler function, which returns only job/owner IDs across accounts.
5. **Blocked pending least-privilege implementation:** do not use an `sb_secret_...`, legacy `service_role` key, or S3 access key for this worker. Supabase documents these as project-wide or all-buckets credentials that bypass RLS. The selected design is user-JWT Storage API access (`apikey` plus the owner's short-lived JWT), backed by a short-lived, random-path upload authorization created by the worker only after scanning; Storage RLS will permit only that exact owner/path insert, with no upsert. A durable encrypted worker Auth refresh-session lifecycle is also required for unattended polling; the current browser session is not sufficient after sign-out. Add local policy tests for missing/expired/replayed/cross-owner tickets and a real Storage HTTP test before applying a Storage policy or enabling Gmail.
6. **Do not run the configuration helper yet.** It now fails closed until the RLS-scoped uploader is implemented. Once that gate is complete, securely configure credentials locally (never in command arguments or chat):
   ```powershell
   $env:PYTHONPATH='.'
   .venv/Scripts/python scripts/configure-pipeline.py
   ```
   The future helper must collect a TLS-verified PostgreSQL URL, the RLS-scoped user-session configuration, and Google client ID/secret through hidden prompts; it must keep `live_imports_enabled=false`. Existing configuration and encryption keys must never be overwritten. Restrict local file access and never print/upload secrets.
7. Configure and verify local security services:
   ```powershell
   docker compose -f infra/compose.yaml --profile ingestion up -d redis clamav
   docker build -f infra/Dockerfile.parser -t certvault-parser:dev .
   ```
   ClamAV initially downloads signatures and can need time to become ready. Port 3310 is loopback-only and unauthenticated: never expose it. Config enforces size/recursion bounds and alerts on scan-limit exhaustion. The parser gets only one read-only PDF, no network, capabilities or secrets, a read-only filesystem, non-root UID, 256 MiB memory, one CPU and a time limit. The worker needs Docker access; never mount the Docker socket into the untrusted parser. Production requires a separately reviewed isolation/deployment arrangement and digest-pinned images.
8. After explicit approval for a bounded test and successful preflight, the developer enables `live_imports_enabled` in ignored config. Restart API/worker. **Do not flip this flag merely to remove the disabled banner.** No real test or activation was authorized/executed during implementation.
9. Start the API with access logging disabled, Next.js, worker and scheduler in separate terminals:
   ```powershell
   .venv/Scripts/python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --no-access-log
   pnpm dev
   .venv/Scripts/python -m celery -A apps.worker.celery_app:celery worker --pool=solo --queues=celery,ingestion --concurrency=1 --loglevel=WARNING
   .venv/Scripts/python -m celery -A apps.worker.celery_app:celery beat --loglevel=WARNING --schedule=.local/celerybeat-schedule
   ```
   Windows solo is for development; Celery process time limits require a supported Linux worker pool for production. Network/scanner/parser operations also have their own bounds. Run one Beat scheduler only. Do not configure HTTP client debug/request logging or trace credential-bearing browser tests.
10. Sign into `/account`, choose **Past 7 days**, leave automatic scans **off**, check consent and connect the dedicated test mailbox. Authorize on Google's site. Click **Scan now** for the first approved test. Verify one synthetic PDF appears, downloads privately and does not duplicate on a second scan. Test oversized approval, rejection, outage recovery and owner denial before opting into automatic scans. Google Testing refresh credentials may expire after seven days; reconnect when necessary.

## Verification and limits

Database-free local antivirus/parser smoke (synthetic files only):
```powershell
$env:PYTHONPATH='.'
.venv/Scripts/python scripts/check-security.py
```
This waits up to 180 seconds for signature readiness, checks clean/EICAR handling, inspects actual parser restrictions and exercises extraction/malformed-file rejection. It neither connects accounts nor accesses databases. Redis and ClamAV should report healthy in `docker compose -f infra/compose.yaml ps`; ClamAV's explicit Compose health probe uses the mounted configuration.

Repeat transactional tests against a disposable migrated local database, never a user database:
```powershell
$env:CERTVAULT_TEST_DATABASE_URL='postgresql://postgres:local-test-only@127.0.0.1:54329/certvault_test'
$env:PGPASSWORD='local-test-only'
psql --host 127.0.0.1 --port 54329 --username postgres --dbname certvault_test --file infra/sql/test-ingest-role.sql
$env:CERTVAULT_TEST_SECURITY='1' # requires real local ClamAV + built parser
.venv/Scripts/python -m pytest -q
$env:PLAYWRIGHT_CHANNEL='chrome'
pnpm e2e
```
The role-security SQL script creates a synthetic login only inside a transaction and rolls it back; it checks NOINHERIT/no-admin flags, no inherited pipeline table access, and successful `SET ROLE certvault_pipeline`. Never run it against Supabase or another shared database. `PGPASSWORD` above is the disposable Compose test password only; clear it after local testing.
Provider/Storage requests in these tests are explicitly mocked; real ClamAV and Docker parsing can run in the same orchestration. No test result substitutes for actual provider consent and Storage HTTP verification. CI reruns the PostgreSQL suite after all migrations, skipping the security-service smoke unless configured.

Remaining scope: Outlook orchestration, link references/fetching, inline PDFs without attachment IDs, scanned/image OCR, ambiguous-message review/classification and structured metadata are not completed. Detection currently requires a PDF filename and certificate/credential/achievement wording in the subject; it can miss certificates. Filename supplies a review-needed title; issuer/dates are not invented. High-volume history pages over 200 changes require review/backfill improvement. Account signup/reset, full main-dashboard integration, pagination/privacy/deletion/retention and production hardening remain separate release work.

Retries have exponential scheduling and capped attempts, but exhaustive crash/large-file/load testing and provider-specific Retry-After handling remain outstanding. A disconnect/crash between the scanned-object upload and DB commit can leave a private hash-addressed orphan; resuming reuses the same object, but audited orphan-retention cleanup remains to be implemented. Existing files are never silently deleted to compensate. UI notifications are persisted transactionally, not emailed. Production mode still fails closed. Do not represent this milestone as production-ready.
