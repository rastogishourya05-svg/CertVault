import { test, expect } from "@playwright/test";

test.use({
  permissions: ["microphone"],
  launchOptions: {
    args: [
      "--use-fake-device-for-media-stream",
      "--use-fake-ui-for-media-stream",
    ],
  },
});

test("voice search and corrections use reviewed text and explicit audio consent", async ({
  page,
}) => {
  let sent = 0,
    configured = true;
  const cert = {
    id: "11111111-1111-4111-8111-111111111111",
    title: "Workshop",
    issuer: "Original issuer",
    favorite: false,
    category: "Other",
    source: "manual",
    issued_on: null,
  };
  let saved = "", nextTranscript = "";
  await page.route("**/api/account/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (path.endsWith("/voice/status")) body = { configured };
    else if (path.endsWith("/voice/transcribe")) {
      expect(route.request().headers()["x-certvault-voice-consent"]).toBe(
        "send-recording",
      );
      const size = route.request().postDataBuffer()?.length ?? 0;
      expect(size).toBeGreaterThan(0);
      expect(size).toBeLessThanOrEqual(480000);
      sent++;
      body = { text: nextTranscript };
    } else if (path.endsWith("/pipeline/status"))
      body = {
        enabled: false,
        connections: [],
        imports: [],
        jobs: [],
        notifications: [],
      };
    else if (path.endsWith("/config")) body = { configured: true };
    else if (path.endsWith("/status")) body = { authenticated: true };
    else if (path.endsWith("/profile"))
      body = { display_name: "Fixture", download_limit_bytes: 50000000 };
    else if (path.endsWith("/certificates")) body = [cert];
    else if (path.endsWith("/review")) {
      saved = route.request().postDataJSON().issuer;
      cert.issuer = saved;
    }
    await route.fulfill({ json: body });
  });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/account#private-vault");
  async function dictate(field: string, transcript = "Reviewed " + field) {
    nextTranscript = transcript;
    const before = sent;
    await page
      .getByRole("button", { name: "Dictate " + field, exact: true })
      .click();
    const stop = page.getByRole("button", { name: "Stop recording" });
    await expect(stop).toBeVisible();
    await page.waitForTimeout(350);
    await stop.click();
    await expect.poll(() => sent).toBe(before + 1);
  }
  await dictate("search");
  await expect(page.getByLabel("Search development certificates")).toHaveValue(
    "Reviewed search",
  );
  await page.getByRole("button", { name: "Review extracted details" }).click();
  const beforeCancel = sent;
  await page.getByRole("button", { name: "Dictate title", exact: true }).click();
  await expect(page.getByRole("button", { name: "Stop recording" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel dictation" }).click();
  expect(sent).toBe(beforeCancel);
  await expect(page.getByLabel("Title", {exact:true})).toHaveValue("Workshop");
  nextTranscript = "Alex";
  await page.getByRole("button", { name: "Dictate recipient", exact: true }).click();
  await expect(page.getByLabel("Recipient", {exact:true})).toHaveValue("Alex", {timeout:22000});
  await dictate("issuer");
  expect(saved).toBe("");
  await expect(page.getByLabel("Issuer", { exact: true })).toHaveValue(
    "Reviewed issuer",
  );
  await page.getByText("Correct several fields by voice").click();
  await dictate("field corrections", "Issuer is Reviewed issuer, recipient is Alex, and issue date is 2025-05-14");
  await expect(page.getByLabel("Recipient", {exact:true})).toHaveValue("Alex");
  await expect(page.getByLabel("Issue date", {exact:true})).toHaveValue("2025-05-14");
  expect(saved).toBe("");
  await page.getByRole("button", { name: "Save reviewed details" }).click();
  await expect.poll(() => saved).toBe("Reviewed issuer");
  configured = false;
  await page.getByRole("button", { name: "Dictate search" }).click();
  await expect(page.getByText(/Voice input needs an ElevenLabs key/)).toBeVisible();
  await page.getByLabel("Search development certificates").fill("Typed search");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path:test.info().outputPath("voice-vault.png")});
  expect(errors).toEqual([]);
});
