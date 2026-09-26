import path from "node:path";

import { expect, test } from "@playwright/test";

const SAMPLE_CSV = path.resolve(__dirname, "../../api/tests/fixtures/sample.csv");

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

  // The mock analyst and Gamma client take ~1s and ~2s, so the running states are observable.
  await expect(page.getByRole("heading", { name: "Dataset profile" })).toBeVisible();
  await expect(page.getByText("Completed", { exact: true })).toBeVisible({ timeout: 20_000 });

  await expect(tracker.getByRole("listitem")).toHaveCount(4);
  await expect(page.getByRole("heading", { name: "Your deck is ready" })).toBeVisible();
  await expect(page.getByRole("link", { name: /open in gamma/i })).toHaveAttribute(
    "href",
    /gamma\.app\/docs\/mock-/,
  );
  await expect(page.getByText(/mock mode/i)).toBeVisible();

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
