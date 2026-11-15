import { expect, test } from "@playwright/test";

test("mocked automation activity requires consent and handles per-file approval and disconnect", async ({
  page,
}) => {
  let connected = true;
  let status = "awaiting_approval";
  let scans = 0;
  let decision: unknown;
  await page.route("**/api/account/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (path.endsWith("/config")) body = { configured: true };
    else if (path.endsWith("/account/status")) body = { authenticated: true };
    else if (path.endsWith("/profile"))
      body = {
        display_name: "Mocked automation account",
        download_limit_bytes: 52428800,
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
                automatic: true,
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
          {
            id: "item",
            filename: "Synthetic large certificate.pdf",
            declared_bytes: 53477376,
            status,
            safe_error: null,
          },
        ],
        notifications: [],
      };
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
  await page.goto("/account");
  await expect(
    page.getByRole("heading", { name: "Automatic certificate imports" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Connect Gmail securely" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Scan now" }).click();
  await expect(page.getByText("Scan queued", { exact: true })).toBeVisible();
  expect(scans).toBe(1);
  await page.getByRole("button", { name: "Approve download" }).click();
  expect(decision).toEqual({ approve: true });
  await expect(
    page.getByRole("button", { name: "Approve download" }),
  ).toHaveCount(0);
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
  await page.screenshot({
    path: `../../docs/evidence/pipeline-${test.info().project.name}.png`,
    fullPage: true,
  });
});
