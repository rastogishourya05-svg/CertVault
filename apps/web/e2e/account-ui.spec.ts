import { expect, test } from "@playwright/test";

test("account favorite preserves nullable issuer and searches preserve unsaved profile edits", async ({
  page,
}) => {
  const certificate = {
    id: "11111111-1111-4111-8111-111111111111",
    title: "Protocol fixture",
    issuer: null,
    category: "Other",
    source: "Mocked account API",
    favorite: false,
    issued_on: null,
  };
  let favoritePayload: unknown = null;
  await page.route("**/api/account/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let body: unknown = {};
    if (path.endsWith("/pipeline/status"))
      body = {
        enabled: false,
        reason: "Mocked configuration: live imports disabled.",
        connections: [],
        jobs: [],
        imports: [],
        notifications: [],
      };
    else if (path.endsWith("/config"))
      body = { configured: true, uploads_enabled: false };
    else if (path.endsWith("/status")) body = { authenticated: false };
    else if (path.endsWith("/login")) body = { authenticated: true };
    else if (path.endsWith("/profile"))
      body = {
        display_name: "Mocked account learner",
        download_limit_bytes: 52428800,
      };
    else if (path.endsWith("/favorite")) {
      favoritePayload = request.postDataJSON();
      certificate.favorite = true;
      body = { ok: true };
    } else if (path.endsWith("/certificates")) body = [certificate];
    else throw new Error(`Unexpected mocked account route ${path}`);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  await page.goto("/account");
  await page.getByLabel("Email address").fill("fixture@example.test");
  await page
    .getByLabel("Password", { exact: true })
    .fill("non-secret-mock-password");
  await page.getByRole("button", { name: "Sign in securely" }).click();
  await expect(
    page.getByText("Protocol fixture", { exact: true }).first(),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Favorite Protocol fixture", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Unfavorite Protocol fixture",
      exact: true,
    }),
  ).toBeVisible();
  expect(favoritePayload).toEqual({ value: true });
  await page.getByLabel("Display name").fill("Unsaved personal choice");
  const result = page.waitForResponse((r) =>
    r.url().includes("/api/account/certificates?q=search"),
  );
  await page.getByLabel("Search development certificates").fill("search");
  await result;
  await expect(page.getByLabel("Display name")).toHaveValue(
    "Unsaved personal choice",
  );
});
