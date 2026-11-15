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
    fs.readFileSync(path.resolve("../../.local/account-test.json"), "utf8"),
  );
  const index = test.info().project.name === "mobile" ? 1 : 0;
  const label = "AB"[index];
  const account = fixture.accounts[index];
  await page.goto("/account");
  await page.getByLabel("Email address").fill(account.email);
  await page.getByLabel("Password", { exact: true }).fill(account.password);
  await page.getByRole("button", { name: "Sign in securely" }).click();
  await expect(
    page
      .getByText(`Synthetic hosted credential ${label}`, { exact: true })
      .first(),
  ).toBeVisible();
  await expect(
    page.getByText(`Synthetic hosted credential ${"BA"[index]}`, {
      exact: true,
    }),
  ).toHaveCount(0);
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
