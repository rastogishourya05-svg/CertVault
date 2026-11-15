# CertVault — Product Requirements Document

## Product vision
A private-by-default, automation-first web platform that discovers certificate-related emails with user consent, safely imports available credentials, organizes them, notifies users, and lets users selectively share credentials or draft social posts.

## Primary users
Students, job applicants, working professionals; later issuers/institutions. Multi-tenant accounts; users only see their own private data.

## Core user journey
Sign up -> connect Gmail/Outlook via provider OAuth -> choose scan scope and consent -> initial backfill -> automatic incremental processing -> detect likely certificates -> enforce download-size policy -> download safe supported files -> extract metadata -> deduplicate -> save to private vault -> notify -> review/share/post with user approval.

## Functional requirements (priority P0)
- Authentication: sign-up, sign-in, sign-out, password reset; secure session management.
- OAuth email connections: Gmail first, Outlook second; minimal necessary scopes, clear consent, token revocation/disconnect, connection health. Do not confuse Supabase sign-in with Gmail mailbox authorization.
- Mail sync: initial historical scan and incremental sync, pagination, rate limits, provider quotas, dedupe by provider message/attachment IDs, idempotent jobs. Never ingest unrelated emails into permanent storage.
- Detection: rule-based candidate selection (subject/sender/attachment/link), AI classifier for ambiguous cases, confidence score and review queue.
- Attachments: inspect declared size and content type; default auto-download limit 50 MiB, configurable by user within admin hard cap; oversized files become `awaiting_approval` and MUST NOT be downloaded to persistent storage until per-file approval. For unknown sizes, bounded streaming into temporary quarantine, stop at threshold and request approval. Admin hard cap remains enforced even after approval.
- Links: allowlisted HTTPS fetch policy, redirect validation, DNS/IP SSRF defense, timeouts, size bounds, no credential sharing, no bypass of login/CAPTCHA; unsupported links stored as references with actionable review.
- Files: MIME sniffing, malware scanning, PDF/image validation, quarantine, private object storage, encryption at rest, signed access URLs, hash-based duplicate detection.
- Extraction: PyMuPDF text extraction, OCR for scans, structured LLM fallback; extract title, issuer, recipient, issue/expiry date, credential ID, verification URL, skill tags, source; confidence and provenance for fields; do not invent missing values. Extraction is NOT authenticity verification.
- Vault: grid/list, preview, full-text search, filters, tags, collections, favorites, edit metadata, download, trash/recovery, export, manual upload, bulk actions.
- Notifications: in-app on successful import, approval needed, errors, review needed, duplicate, expiry; user preferences, read/unread, no duplicate events.
- Audit: user-visible import history, job states, errors, permission changes.
- UX: polished, responsive, accessible dashboard with onboarding, progress, actionable errors, skeletons, empty states and dark mode.

## P1
- Multiple mailboxes per account, Outlook integration, more certificate link providers.
- Public opt-in profile, featured credentials, shareable collections, expiring/revocable private share links, QR codes.
- Social sharing: WhatsApp/share sheet, copy caption and certificate link; LinkedIn-ready post and profile credential instructions; direct publishing ONLY if officially supported and authorized.
- AI post studio: professional/friendly/short tones, editable preview, hashtags, draft history; never publish automatically.
- Browser/email notification options, digest, expiry reminders.
- AI assistant for vault search and suggestions; require confirmation for mutations.

## P2
- Browser extension, job-specific certificate packs, skills graph, resume exports, issuer verification integrations, institution workspace, embeddable profile widgets.

## Explicit non-goals / guardrails
- No claim of guaranteed certificate authenticity or automatic LinkedIn publishing.
- No autonomous login bypass, scraping behind CAPTCHAs, unrestricted web crawling, or unrestricted AI agent tool access.
- No public disclosure of imported certificates without opt-in.
- No claim that a 50 MiB size limit makes an attachment safe.

## Acceptance criteria
- A consented Gmail test mailbox with sample certificate PDF can be imported end-to-end and appears in private vault with notification.
- A 51 MiB attachment with a 50 MiB threshold is not auto-imported; it appears in approval queue; denial leaves it unimported.
- An unknown-size stream is stopped safely at the configured bound.
- Reprocessing same message never creates duplicate stored credentials or notifications.
- Unrelated emails are not imported as certificates.
- Revoking/disconnecting email stops future sync; existing imported data is retained/deleted according to explicit user choice.
- Users cannot access other users' certificates, storage objects, notifications, or share links without authorization.
- Sharing is opt-in; generated posts are editable and never auto-published.
- Web UI works on mobile and desktop with keyboard navigation and clear errors.
