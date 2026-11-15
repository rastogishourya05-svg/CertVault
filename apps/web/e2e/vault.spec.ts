import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

async function navigate(page: Page, name: string) {
  if (
    await page
      .getByRole("button", { name: "Open navigation", exact: true })
      .isVisible()
  )
    await page
      .getByRole("button", { name: "Open navigation", exact: true })
      .click();
  await page
    .locator("aside")
    .getByRole("button", { name, exact: true })
    .click();
}

test("sample import, approval, vault, drafts, sharing, privacy, trash and notifications", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Explore local demo" }).click();
  await expect(
    page.getByText("Your story is still being collected."),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Connect sample mailbox", exact: true })
    .click();
  await expect(
    page
      .getByRole("button", { name: "Connect sample mailbox", exact: true })
      .last(),
  ).toBeDisabled();
  await page.getByRole("checkbox").check();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Connect sample mailbox" })
    .click();
  await page.getByRole("button", { name: "Scan samples" }).click();
  await expect(
    page.getByText(
      "Sample scan complete. Check your vault and approval inbox.",
    ),
  ).toBeVisible();
  await navigate(page, "Overview");
  await expect(
    page.getByRole("button", {
      name: "Preview Cloud Architecture Foundations",
    }),
  ).toBeVisible();
  await page.screenshot({
    path: `../../docs/evidence/${testInfo.project.name}-overview.png`,
    fullPage: true,
  });
  await navigate(page, "Approval inbox");
  await page.getByRole("button", { name: "Approve download" }).click();
  await expect(
    page.getByText("Approved sample imported privately."),
  ).toBeVisible();
  await expect(page.getByText("All clear. You're in control.")).toBeVisible();
  await navigate(page, "Connected mailboxes");
  await page.getByRole("button", { name: "Scan samples" }).click();
  await expect(
    page.getByText(
      "Sample scan complete. Check your vault and approval inbox.",
    ),
  ).toBeVisible();
  await navigate(page, "My vault");
  await expect(page.getByRole("button", { name: /^Preview / })).toHaveCount(4);
  await page
    .getByRole("textbox", { name: "Search certificates" })
    .fill("Cloud");
  await expect(page.getByRole("button", { name: /^Preview / })).toHaveCount(1);
  await page
    .getByRole("button", {
      name: "Favorite Cloud Architecture Foundations",
      exact: true,
    })
    .click();
  await page
    .getByRole("button", { name: "Preview Cloud Architecture Foundations" })
    .click();
  await page
    .getByLabel("Certificate title", { exact: true })
    .fill("Cloud Architecture Milestone");
  await page.getByRole("button", { name: "Save details", exact: true }).click();
  await expect(page.getByText("Certificate details saved.")).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download PDF" }).click();
  expect((await downloadPromise).suggestedFilename()).toBe("certificate.pdf");
  await page.getByRole("checkbox", { name: /Allow anyone/ }).check();
  await page
    .getByRole("button", { name: "Create expiring share link" })
    .click();
  await expect(page.getByLabel("Local share link")).toHaveValue(
    /\/api\/shared\//,
  );
  await page.getByRole("button", { name: "Close dialog" }).click();
  await navigate(page, "Sharing");
  await page.getByRole("button", { name: "Revoke access" }).click();
  await expect(page.getByText("Share link revoked.")).toBeVisible();
  await navigate(page, "Post studio");
  await page
    .getByRole("combobox", { name: "Certificate", exact: true })
    .selectOption({ label: "Cloud Architecture Milestone" });
  await page.getByRole("button", { name: "Create template draft" }).click();
  await expect(page.getByLabel("Your editable caption")).toHaveValue(
    /Cloud Architecture Milestone/,
  );
  await page
    .getByLabel("Your editable caption")
    .fill("Proud of this new milestone.");
  await page.getByRole("button", { name: "Save edits" }).click();
  await expect(page.getByText("Draft saved.")).toBeVisible();
  await navigate(page, "Public profile");
  await page.getByLabel("Profile address").fill(`learner-${Date.now()}`);
  await page
    .getByRole("checkbox", {
      name: "Cloud Architecture Milestone",
      exact: true,
    })
    .check();
  await page
    .getByRole("checkbox", { name: "Enable my public profile" })
    .check();
  await page.getByRole("checkbox", { name: /I confirm/ }).check();
  await page.getByRole("button", { name: "Save profile choices" }).click();
  await expect(
    page.getByRole("link", { name: "View local profile" }),
  ).toBeVisible();
  await navigate(page, "My vault");
  await page
    .getByRole("button", { name: "Preview Cloud Architecture Milestone" })
    .click();
  await page.getByRole("button", { name: "Move to trash" }).click();
  await expect(
    page.getByText("Moved to trash. Any share links were revoked."),
  ).toBeVisible();
  await navigate(page, "Trash");
  await page
    .getByRole("button", { name: "Preview Cloud Architecture Milestone" })
    .click();
  await page.getByRole("button", { name: "Restore certificate" }).click();
  await expect(page.getByText("Certificate restored.")).toBeVisible();
  await page.getByRole("button", { name: /^Notifications/ }).click();
  await page.getByRole("button", { name: "Mark all as read" }).click();
  await expect(
    page.getByRole("button", { name: "Mark all as read" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Close dialog" }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});

test("rejection and disconnected sample mailbox do not import oversized certificate", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Explore local demo" }).click();
  await page
    .getByRole("button", { name: "Connect sample mailbox", exact: true })
    .click();
  await page.getByRole("checkbox").check();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Connect sample mailbox" })
    .click();
  await page.getByRole("button", { name: "Scan samples" }).click();
  await expect(
    page.getByText(
      "Sample scan complete. Check your vault and approval inbox.",
    ),
  ).toBeVisible();
  await navigate(page, "Approval inbox");
  await page.getByRole("button", { name: "Reject", exact: true }).click();
  await expect(
    page.getByText("Import rejected. No file was stored."),
  ).toBeVisible();
  await navigate(page, "Connected mailboxes");
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(
    page.getByText("Disconnected · Existing imports retained"),
  ).toBeVisible();
  await navigate(page, "My vault");
  await expect(page.getByRole("button", { name: /^Preview / })).toHaveCount(3);
});

test("manual upload validates content and keyboard dialogs return focus", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Explore local demo" }).click();
  const add = page.getByRole("button", {
    name: "Add certificate",
    exact: true,
  });
  await add.click();
  await page.getByLabel("Choose sample PDF").setInputFiles({
    name: "unsafe.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("not a PDF"),
  });
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "Only PDF content",
  );
  await page
    .getByLabel("Choose sample PDF")
    .setInputFiles(path.resolve("../../tests/fixtures/sample.pdf"));
  await expect(
    page.getByText("PDF added. Review the title and issuer before sharing."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Preview sample" }),
  ).toBeVisible();
  await page.reload();
  await page
    .getByRole("textbox", { name: "Search certificates" })
    .fill("Manual upload fixture");
  await expect(
    page.getByRole("button", { name: "Preview sample" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /^Preview / })).toHaveCount(1);
  await page.getByRole("textbox", { name: "Search certificates" }).fill("");
  await add.click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(add).toBeFocused();
});

test("collections, tags and bulk organization stay private", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Explore local demo" }).click();
  await page
    .getByRole("button", { name: "Connect sample mailbox", exact: true })
    .click();
  await page.getByRole("checkbox").check();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Connect sample mailbox" })
    .click();
  await page.getByRole("button", { name: "Scan samples" }).click();
  await expect(
    page.getByText(
      "Sample scan complete. Check your vault and approval inbox.",
    ),
  ).toBeVisible();
  await navigate(page, "My vault");
  await page
    .getByRole("button", { name: "Preview Cloud Architecture Foundations" })
    .click();
  await page.getByLabel("Tags (comma-separated)").fill("cloud, career");
  await page.getByRole("button", { name: "Save details", exact: true }).click();
  await expect(page.getByText("Certificate details saved.")).toBeVisible();
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page
    .getByRole("textbox", { name: "Search certificates" })
    .fill("career");
  await expect(page.getByRole("button", { name: /^Preview / })).toHaveCount(1);
  await navigate(page, "Collections");
  await page.getByLabel("Collection name").fill("Next opportunity");
  await page
    .getByRole("checkbox", {
      name: "Cloud Architecture Foundations",
      exact: true,
    })
    .check();
  await page.getByRole("button", { name: "Save collection" }).click();
  await expect(page.getByText("Private collection saved.")).toBeVisible();
  await navigate(page, "My vault");
  await page
    .getByRole("button", { name: "Select certificates", exact: true })
    .click();
  await page
    .getByRole("checkbox", {
      name: "Select Cloud Architecture Foundations",
      exact: true,
    })
    .check();
  await page.getByRole("button", { name: "Move selected to trash" }).click();
  await expect(
    page.getByText(
      "Selected certificates moved to trash; share links revoked.",
    ),
  ).toBeVisible();
  await navigate(page, "Trash");
  await page
    .getByRole("button", { name: "Select certificates", exact: true })
    .click();
  await page
    .getByRole("checkbox", {
      name: "Select Cloud Architecture Foundations",
      exact: true,
    })
    .check();
  await page.getByRole("button", { name: "Restore selected" }).click();
  await expect(page.getByText("Selected certificates restored.")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
