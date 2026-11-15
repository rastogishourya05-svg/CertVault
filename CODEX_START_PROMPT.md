# Paste this into Codex in the repository root

You are the lead full-stack engineer, product designer, QA engineer, and security reviewer for CertVault. The repo contains authoritative requirements in AGENTS.md and docs/*.md. Read all of them and the project skill before coding.

Your task is to implement the complete CertVault product in staged, independently testable vertical slices. Begin by inspecting the repo and environment. Produce a short execution plan and keep docs/IMPLEMENTATION_STATUS.md updated. Then scaffold a clean monorepo with Next.js/TypeScript/Tailwind/shadcn/ui frontend, FastAPI Python backend, Celery/Redis worker, Supabase Auth/Postgres/private Storage, database migrations, Docker local development, and Playwright/pytest/Vitest testing.

Design a distinctive, professional, accessible, mobile-responsive UI using deep navy, blue and cyan, excellent typography, consistent components, polished loading/empty/error states, and real functional interactions. Do not build a static mockup and call it finished. Use browser automation to inspect desktop and mobile, take screenshots and fix visible issues.

Implement P0 requirements end-to-end before P1, then P2 if feasible. Prioritize working OAuth-safe email import, bounded download policy, approval queue, document extraction, private vault, dedupe and notifications. Use provider mocks in local tests until real credentials are supplied. Never fake successful Gmail/Outlook/LinkedIn integration. Implement external integrations behind adapters with documented credentials and fallback flows. No automatic social posting.

For each slice, write migrations, backend, frontend, tests, run all checks and browser QA, fix failures, and commit coherent changes if git is configured. Do not ask me to perform routine coding, dependency installation, file creation or test execution that you can do yourself. Ask only for required human authorization, secrets, external provider approvals, or irreversible deployment decisions. Never reveal secrets or bypass security requirements.

At the end, report precisely what is implemented, which commands and tests actually passed, screenshots reviewed, what remains, and any external credentials/approvals needed. Continue through the plan rather than stopping after scaffold, but do not misrepresent unfinished work as complete.
