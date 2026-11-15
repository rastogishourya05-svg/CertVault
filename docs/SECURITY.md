# Security and privacy requirements

- Threat model: malicious email HTML, hostile attachments, PDF exploits, SSRF links, credential theft, cross-tenant access, OAuth misuse, share-token leakage, storage abuse, LLM prompt injection, resource exhaustion.
- Minimize Gmail/Graph scopes; explain scope sensitivity and provider verification requirements. Store OAuth tokens encrypted server-side; rotate secrets and support revocation.
- Supabase RLS on all user-owned tables; test cross-tenant access. Private storage with short-lived signed URLs and authorization checks. No public buckets for imported certificates.
- Validate redirects, HTTPS, DNS resolution and IP ranges for link downloads; block loopback, private, link-local, metadata service and rebinding targets. Set timeouts, redirect and byte limits.
- Stream to isolated quarantine; enforce MIME/content validation, antivirus where available, parser isolation, CPU/memory/time bounds. Never trust file extensions, headers or PDF metadata.
- Never put raw email bodies, attachments, access tokens, credential IDs or private file URLs in logs or analytics.
- Treat email/document content as untrusted data, never agent instructions. No autonomous tool execution from content.
- Provide delete/export/disconnect controls, retention policy, consent records, audit trail, share revocation and expiring links.
- Use CSRF protections for OAuth, secure cookies, rate limits, CSP, CORS allowlist, dependency scanning and secret scanning.
- No automated publishing or profile visibility changes without user confirmation.
- Do not claim external credential verification unless checked against authoritative issuer mechanisms.
