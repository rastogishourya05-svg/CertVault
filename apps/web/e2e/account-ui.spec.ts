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
    } else if (path.endsWith("/certificates"))
      body = [
        {
          ...certificate,
          certificate_files: [{ mime: "application/pdf", bytes: 236406 }],
        },
        {
          ...certificate,
          id: "22222222-2222-4222-8222-222222222222",
          certificate_files: [{ mime: "image/jpeg", bytes: 236413 }],
        },
      ];
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
  await page.getByRole("link", { name: "My vault", exact: true }).click();
  await expect(
    page.getByText("Protocol fixture", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText(/Same title as another file/)).toHaveCount(2);
  await expect(page.getByText(/PDF.*236,406 bytes/)).toBeVisible();
  await expect(page.getByText(/JPEG.*236,413 bytes/)).toBeVisible();
  await page
    .getByRole("button", { name: "Favorite Protocol fixture", exact: true })
    .first()
    .click();
  await expect(
    page
      .getByRole("button", {
        name: "Unfavorite Protocol fixture",
        exact: true,
      })
      .first(),
  ).toBeVisible();
  expect(favoritePayload).toEqual({ value: true });
  await page.getByRole("link", { name: "Preferences", exact: true }).click();
  await page.getByLabel("Display name").fill("Unsaved personal choice");
  await page.getByRole("link", { name: "My vault", exact: true }).click();
  const result = page.waitForResponse((r) =>
    r.url().includes("/api/account/certificates?q=search"),
  );
  await page.getByLabel("Search development certificates").fill("search");
  await result;
  await page.getByRole("link", { name: "Preferences", exact: true }).click();
  await expect(page.getByLabel("Display name")).toHaveValue(
    "Unsaved personal choice",
  );
});

test("signed-in overview, collection membership and favorites use account endpoints", async ({
  page,
}) => {
  const cert = {
    id: "cert1",
    title: "Synthetic Cloud Systems",
    issuer: "Fixture Academy",
    source: "manual",
    favorite: true,
    category: "Technology",
  };
  const groups: {
    id: string;
    name: string;
    collection_items: { certificate_id: string }[];
  }[] = [];
  await page.route("**/api/account/**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname;
    if (path.endsWith("/config"))
      return route.fulfill({ json: { configured: true } });
    if (path.endsWith("/pipeline/status"))
      return route.fulfill({
        json: {
          enabled: true,
          connections: [],
          jobs: [],
          imports: [],
          notifications: [],
        },
      });
    if (path.endsWith("/status"))
      return route.fulfill({ json: { authenticated: true } });
    if (path.endsWith("/profile"))
      return route.fulfill({
        json: {
          display_name: "Synthetic workspace",
          download_limit_bytes: 50000000,
        },
      });
    if (path.endsWith("/certificates")) return route.fulfill({ json: [cert] });
    if (path.endsWith("/organization/collections")) {
      if (req.method() === "POST")
        groups.push({
          id: "group1",
          name: req.postDataJSON().name,
          collection_items: [],
        });
      return route.fulfill({ json: groups });
    }
    if (path.endsWith("/collections/group1/cert1")) {
      groups[0].collection_items =
        req.method() === "PUT" ? [{ certificate_id: "cert1" }] : [];
      return route.fulfill({ json: { ok: true } });
    }
    throw Error("Unexpected account endpoint");
  });
  await page.goto("/account");
  await expect(
    page.getByRole("link", { name: "Certificates in vault 1" }),
  ).toBeVisible();
  await page.screenshot({
    path: `../../docs/evidence/account-overview-${test.info().project.name}.png`,
    fullPage: true,
  });
  await page.getByRole("link", { name: "Collections & tags" }).click();
  await page.getByLabel("New collection name").fill("Cloud");
  await page.getByRole("button", { name: "Create collection" }).click();
  await page.getByRole("checkbox", { name: cert.title }).check();
  await expect(page.getByRole("checkbox", { name: cert.title })).toBeEnabled();
  await page.reload();
  await page.getByLabel("Manage membership").selectOption("group1");
  await expect(page.getByRole("checkbox", { name: cert.title })).toBeChecked();
  await page.getByRole("checkbox", { name: cert.title }).uncheck();
  await page.getByRole("link", { name: "My vault", exact: true }).click();
  await page.getByRole("button", { name: "Favorites only" }).click();
  await page.getByRole("button", { name: "Switch to list" }).click();
  await expect(page.getByRole("heading", { name: cert.title })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});
