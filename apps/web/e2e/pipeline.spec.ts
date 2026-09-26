import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const SAMPLE_CSV = path.resolve(__dirname, "../../api/tests/fixtures/sample.csv");

/** Slide parts inside a .pptx (a zip): the central directory lists every entry name. */
function countSlides(pptx: Buffer): number {
  const names = pptx.toString("latin1").match(/ppt\/slides\/slide\d+\.xml/g) ?? [];
  return new Set(names).size;
}

test("upload → progress → insights, profile and deck", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Upload dataset").setInputFiles(SAMPLE_CSV);
  await expect(page.getByText("sample.csv")).toBeVisible();

  await page.getByLabel("Slides").fill("6");
  await page.getByLabel("Audience").fill("the leadership team");
  await page.getByRole("button", { name: /analyze and build deck/i }).click();

  await expect(page).toHaveURL(/\/jobs\/[0-9a-f]{32}$/);
  const tracker = page.getByRole("list", { name: "Pipeline progress" });
  await expect(tracker).toBeVisible();

  // The mock analyst takes ~1s, so the running state is observable before completion.
  await expect(page.getByRole("heading", { name: "Dataset profile" })).toBeVisible();
  await expect(page.getByText("Completed", { exact: true })).toBeVisible({ timeout: 20_000 });

  await expect(tracker.getByRole("listitem")).toHaveCount(4);
  await expect(page.getByRole("heading", { name: "Your deck is ready" })).toBeVisible();

  // The download is a real, native .pptx with one slide per requested slide.
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: /download \.pptx/i }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("sample-deck.pptx");
  const file = readFileSync(await download.path());
  expect(file.subarray(0, 2).toString()).toBe("PK");
  expect(countSlides(file)).toBe(6);

  // The in-browser preview and presenter mode.
  await expect(page.getByRole("button", { name: /^Open slide/ })).toHaveCount(6);
  await page.getByRole("button", { name: "Present" }).click();
  const dialog = page.getByRole("dialog", { name: "Slide 1 of 6" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("What sample.csv tells us")).toBeVisible();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("dialog", { name: "Slide 3 of 6" })).toContainText("Median units");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await expect(page.getByRole("heading", { name: "Insights" })).toBeVisible();
  await expect(page.getByText("6 slides · executive tone · for the leadership team")).toBeVisible();
  await expect(page.getByRole("cell", { name: "revenue and unit_price: r = 0.78" })).toBeVisible();
  await expect(page.getByRole("row", { name: /order_date datetime/ })).toContainText(
    "2025-01-01 to 2025-10-01",
  );
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
