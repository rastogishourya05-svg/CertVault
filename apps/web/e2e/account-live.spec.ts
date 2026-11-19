import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
test("approved temporary Supabase account signs in, reads private vault and signs out", async ({
  page,
}) => {
  test.skip(
    process.env.CERTVAULT_LIVE_TESTS !== "1",
    "Requires explicitly approved temporary accounts",
  );
  const fixture = JSON.parse(
    fs.readFileSync(
      process.env.CERTVAULT_ACCOUNT_FIXTURE ??
        path.resolve("../../.local/account-test.json"),
      "utf8",
    ),
  );
  const index = test.info().project.name === "mobile" ? 1 : 0;
  const label = "AB"[index];
  const account = fixture.accounts[index];
  await page.goto("/account");
  await page.getByLabel("Email address").fill(account.email);
  await page.getByLabel("Password", { exact: true }).fill(account.password);
  await page.getByRole("button", { name: "Sign in securely" }).click();
  await page.getByRole("link", { name: "My vault", exact: true }).click();
  await expect(
    page
      .getByText(account.title ?? `Synthetic hosted credential ${label}`, {
        exact: true,
      })
      .first(),
  ).toBeVisible();
  await expect(
    page.getByText(
      fixture.accounts[1 - index].title ??
        `Synthetic hosted credential ${"BA"[index]}`,
      {
        exact: true,
      },
    ),
  ).toHaveCount(0);
  if (process.env.CERTVAULT_ACCOUNT_FIXTURE) {
    const pdf = await page
      .getByRole("link", { name: "View PDF", exact: true })
      .getAttribute("href");
    const response = await page.request.get(pdf!);
    expect(response.status()).toBe(200);
    expect((await response.body()).subarray(0, 5).toString()).toBe("%PDF-");
    await page.getByRole("link", { name: "Collections & tags" }).click();
    await page.getByLabel("New collection name").fill("Presentation");
    await page.getByRole("button", { name: "Create collection" }).click();
    await page.getByRole("checkbox", { name: account.title }).check();
    await expect(
      page.getByRole("checkbox", { name: account.title }),
    ).toBeEnabled();
    await page.reload();
    await page
      .getByLabel("Manage membership")
      .selectOption({ label: "Presentation" });
    await expect(
      page.getByRole("checkbox", { name: account.title }),
    ).toBeChecked();
  }
  await page.getByRole("link", { name: "Preferences", exact: true }).click();
  await expect(page.getByLabel("Display name")).toHaveValue(
    `Synthetic learner ${label}`,
  );
  await page.getByLabel("Display name").fill("Synthetic browser learner");
  await page
    .getByRole("button", { name: "Save development preferences" })
    .click();
  await expect(
    page.getByText("Profile saved to your private development account."),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `../../docs/evidence/account-${test.info().project.name}.png`,
    fullPage: true,
    scale: "css",
  });
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Sign in securely" }),
  ).toBeVisible();
});
