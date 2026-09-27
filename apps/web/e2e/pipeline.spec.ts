import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";


/** Slide parts inside a .pptx (a zip): the central directory lists every entry name. */
function countSlides(pptx: Buffer): number {
  const names = pptx.toString("latin1").match(/ppt\/slides\/slide\d+\.xml/g) ?? [];
  return new Set(names).size;
}

test("example dataset → tested findings, answer and a native deck", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /e-commerce orders/i }).click();
  await expect(page.getByText("ecommerce_orders.csv")).toBeVisible();
  await expect(page.getByLabel(/what do you want to learn/i)).toHaveValue(/margin/);
  await expect(page.getByRole("combobox", { name: /outcome to explain/i })).toHaveValue("margin");
  await page.getByLabel("Slides").fill("8");
  await page.getByRole("button", { name: /analyze and build deck/i }).click();

  await expect(page).toHaveURL(/\/jobs\/[0-9a-f]{32}$/);
  await expect(page.getByText("Completed", { exact: true })).toBeVisible({ timeout: 30_000 });

  // The question is answered first, citing findings that exist on the page.
  const answers = page.getByRole("region", { name: "Your question, answered" });
  await expect(answers).toBeVisible();
  const chip = answers.getByRole("link").first();
  const target = await chip.getAttribute("href");
  await expect(page.locator(target!)).toBeVisible();

  // Tested findings, including the planted discount → margin effect.
  const findings = page.getByRole("region", { name: "Findings" });
  await expect(findings.getByRole("heading", { name: "margin falls across discount_pct" })).toBeVisible();
  await expect(page.getByText(/figures traced to the analysis/)).toBeVisible();

  // The download is a real, native .pptx with one slide per requested slide.
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: /download \.pptx/i }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("ecommerce_orders-deck.pptx");
  const file = readFileSync(await download.path());
  expect(file.subarray(0, 2).toString()).toBe("PK");
  expect(countSlides(file)).toBe(8);

  // The in-browser preview and presenter mode.
  await expect(page.getByRole("button", { name: /^Open slide/ })).toHaveCount(8);
  await page.getByRole("button", { name: "Present" }).click();
  await expect(page.getByRole("dialog", { name: "Slide 1 of 8" })).toBeVisible();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("dialog", { name: "Slide 2 of 8" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("a corrupt workbook is rejected with the server's message", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Upload dataset").setInputFiles({
    name: "broken.xlsx",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: Buffer.from("definitely not a workbook"),
  });
  await page.getByRole("button", { name: /analyze and build deck/i }).click();

  // Next.js mounts its own empty role="alert" route announcer, so match on text.
  await expect(page.getByRole("alert").filter({ hasText: /not a valid \.xlsx workbook/ })).toBeVisible();
  await expect(page).toHaveURL(/\/$/);
});
