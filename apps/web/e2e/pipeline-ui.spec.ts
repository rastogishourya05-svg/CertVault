import { expect, test } from "@playwright/test";

test("mocked automation activity requires consent and handles per-file approval and disconnect", async ({
  page,
}) => {
  const browserErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    failedRequests.push(`${request.method()} ${request.url()}`);
  });
  let connected = true;
  let status = "awaiting_approval";
  let scans = 0;
  let reviewed = false;
  let decision: unknown;
  await page.route("**/api/account/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (path.endsWith("/config")) body = { configured: true };
    else if (path.endsWith("/account/status")) body = { authenticated: true };
    else if (path.endsWith("/profile"))
      body = {
        display_name: "Mocked automation account",
        download_limit_bytes: 45 * 1048576,
      };
    else if (path.endsWith("/certificates")) body = [];
    else if (path.endsWith("/pipeline/status"))
      body = {
        enabled: true,
        reason: "Explicitly mocked browser fixture. No mailbox accessed.",
        connections: connected
          ? [
              {
                id: "mailbox",
                account_label: "synthetic@example.test",
                state: "connected",
                automatic: false,
                scan_days: 30,
              },
            ]
          : [],
        jobs: scans
          ? [
              {
                id: "job",
                status: "queued",
                attempts: 0,
                safe_error_code: null,
              },
            ]
          : [],
        imports: [
          { id: "badge", filename: "Issuer link requires manual review", connection_id: "mailbox",
            message_id: "abc", status: reviewed ? "rejected" : "needs_review", declared_bytes: null,
            safe_error: reviewed ? "user_reviewed" : "unsupported_issuer_page" },
          {
            id: "item",
            filename: "Synthetic 49 MB certificate.pdf",
            declared_bytes: 49000000,
            status,
            safe_error: null,
          },
          {
            id: "blocked",
            filename: "Synthetic over-limit certificate.pdf",
            declared_bytes: 50 * 1048576,
            status: "rejected",
            safe_error: "storage_size_limit_exceeded",
          },
        ],
        notifications: [],
      };
    else if (path.endsWith("/badge/review")) { reviewed = true; }
    else if (path.endsWith("/scan")) {
      scans++;
      body = { job_id: "job" };
    } else if (path.endsWith("/decision")) {
      decision = route.request().postDataJSON();
      status = "eligible";
      body = { ok: true };
    } else if (route.request().method() === "DELETE") {
      connected = false;
      body = { provider_revocation_confirmed: true };
    } else throw new Error(`Unexpected fixture route ${path}`);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  await page.goto("/account#mailboxes");
  await expect(
    page.getByRole("heading", { name: "Gmail certificate imports" }),
  ).toBeVisible();
  await expect(page.getByText("Scan on request · Past 30 days")).toBeVisible();
  await page.getByText("Connect a Gmail mailbox", { exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Connect Gmail securely" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Scan now" }).click();
  await page.getByRole("link", { name: "Activity", exact: true }).click();
  await expect(
    page.getByText(/Exceeds the 50 MB \(50,000,000-byte\) Storage limit/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve download" }),
  ).toHaveCount(1);

  await expect(page.getByText("Scan queued", { exact: true })).toBeVisible();
  await page.screenshot({
    path: `../../docs/evidence/pipeline-size-limit-${test.info().project.name}.png`,
    fullPage: true,
  });
  await expect(page.getByRole("link", {name: "Open source email in Gmail"})).toHaveAttribute("href", /#all\/abc$/);
  await page.getByRole("button", {name: "Mark reviewed"}).click();
  await expect(page.getByRole("button", {name: "Mark reviewed"})).toHaveCount(0);
  expect(scans).toBe(1);
  await page.getByRole("link", { name: "Approval inbox", exact: true }).click();
  await page.getByRole("button", { name: "Approve download" }).click();
  expect(decision).toEqual({ approve: true });
  await expect(
    page.getByRole("button", { name: "Approve download" }),
  ).toHaveCount(0);
  await page
    .getByRole("link", { name: "Connected mailboxes", exact: true })
    .click();
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(page.getByRole("button", { name: "Scan now" })).toHaveCount(0);
  await expect(
    page.getByText("Disconnected. Existing certificates are retained."),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
  ).toBe(false);
  expect(browserErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
});

test("empty completed scan explains PDF rules and navigates to vault", async ({
  page,
}) => {
  await page.route("**/api/account/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (path.endsWith("/config")) body = { configured: true };
    else if (path.endsWith("/account/status")) body = { authenticated: true };
    else if (path.endsWith("/profile"))
      body = { display_name: "Synthetic", download_limit_bytes: 50000000 };
    else if (path.endsWith("/certificates")) body = [];
    else if (path.endsWith("/pipeline/status"))
      body = {
        enabled: true,
        reason: "Mocked fixture",
        connections: [],
        jobs: [
          {
            id: "empty",
            summary: {},
            status: "completed",
            attempts: 0,
            safe_error_code: null,
          },
        ],
        imports: [],
        notifications: [],
      };
    await route.fulfill({ json: body });
  });
  await page.goto("/account#activity");
  await expect(
    page.getByText(/Scan finished with no matching certificates/),
  ).toBeVisible();
  await page.getByRole("link", { name: "My vault", exact: true }).click();
  await expect(page).toHaveURL(/#private-vault$/);
  await expect(page.locator("#private-vault")).toBeInViewport();
});

test("issuer review exposes evidence without claiming authenticity", async ({
  page,
}) => {
  await page.route("**/api/account/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (path.endsWith("/config")) body = { configured: true };
    else if (path.endsWith("/account/status")) body = { authenticated: true };
    else if (path.endsWith("/profile"))
      body = { display_name: "Synthetic", download_limit_bytes: 50000000 };
    else if (path.endsWith("/pipeline/status"))
      body = {
        enabled: false,
        reason: "Mocked fixture",
        connections: [],
        jobs: [],
        imports: [],
        notifications: [],
      };
    else if (path.endsWith("/verification"))
      body = {
        credential_id: "ABC12345",
        recipient: "Synthetic learner",
        status: "issuer_review_available",
        explanation: "Compare details on the issuer page.",
        issuer_links: [
          {
            issuer: "Coursera",
            url: "https://www.coursera.org/verify/ABC12345",
          },
        ],
      };
    else if (path.endsWith("/certificates"))
      body = [
        {
          id: "synthetic",
          title: "Synthetic course",
          issuer: "Synthetic issuer",
          category: "Education",
          favorite: false,
          source: "gmail",
          issued_on: null,
        },
      ];
    await route.fulfill({ json: body });
  });
  await page.goto("/account#private-vault");
  await page
    .getByRole("button", { name: "Credential & issuer verification" })
    .click();
  await expect(
    page.getByText("Authenticity: not verified", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Credential ID: ABC12345")).toBeVisible();
  await expect(
    page.getByRole("link", { name: /Review on Coursera/ }),
  ).toHaveAttribute("rel", "noopener noreferrer");
});
