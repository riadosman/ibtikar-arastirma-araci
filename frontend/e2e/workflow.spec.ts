import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
let createdRequestId: string | undefined;
test.afterEach(async ({ page }) => {
  if (createdRequestId) {
    const response = await page.request.delete(`/api/v1/research-requests/${createdRequestId}`, {
      headers: { "X-Requested-With": "RelationshipPlatform" },
    });
    expect(response.status()).toBe(204);
    createdRequestId = undefined;
  }
});
const env = Object.fromEntries(
  readFileSync(resolve(process.cwd(), "../.env"), "utf8")
    .split(/\r?\n/)
    .filter((l) => l.includes("="))
    .map((l) => {
      const i = l.indexOf("=");
      return [l.slice(0, i), l.slice(i + 1)];
    }),
);
test("login, research, review, edit, export and mobile navigation", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Email address").fill(env.ADMIN_EMAIL);
  await page.getByLabel("Password", { exact: true }).fill(env.ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Workspace overview" }),
  ).toBeVisible();
  await page.screenshot({ path: "test-results/dashboard.png", fullPage: true });
  await page
    .getByRole("link", { name: "New research", exact: true })
    .first()
    .click();
  const title = `Browser validation ${Date.now()}`;
  await page.getByLabel("Request title").fill(title);
  await page
    .getByLabel("Description", { exact: true })
    .fill("Validate the complete demo workflow.");
  await page
    .getByLabel("Field", { exact: true })
    .fill("Artificial Intelligence");
  await page.getByLabel("Location", { exact: true }).fill("Istanbul");
  await page
    .getByLabel(/Keywords/)
    .fill("Computer Vision, Machine Learning");
  await page.getByRole("button", { name: "Create research" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  const requestPath = new URL(page.url()).pathname;
  createdRequestId = requestPath.split("/").pop();
  await page.getByRole("button", { name: "Run demo search" }).click();
  await expect(page.getByRole("status").filter({hasText:"12 demo candidates added"})).toBeVisible();
  await page.getByRole("textbox", { name: "Search candidates" }).fill("Maya");
  await expect(
    page.getByRole("link", { name: "View Maya Selin (Demo)", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "View Maya Selin (Demo)", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Maya Selin (Demo)" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Candidate updated");
  await page.getByLabel("Review notes").fill("Reviewed in browser validation.");
  await page.getByRole("button", { name: "Save review" }).click();
  await expect(
    page.getByRole("button", { name: "Approve", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Edit profile" }).click();
  await page
    .getByLabel("Job title", { exact: true })
    .fill("Senior research scientist");
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(
    page.getByRole("heading", { name: "Senior research scientist" }),
  ).toBeVisible();
  await page.goto(requestPath);
  await page
    .getByRole("combobox", { name: "Filter status" })
    .selectOption("APPROVED");
  await expect(page.getByText("1–1 of 1", { exact: true })).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export approved" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.csv$/);
  await page.getByRole("link", { name: "Exports", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Export history" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Users", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Workspace users" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Toggle navigation" }).click();
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Workspace overview" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/mobile-dashboard.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
  // Delete only the request created by this test, through the authorized admin API.
  const rid = requestPath.split("/").pop();
  const removed = await page.request.delete(
    `/api/v1/research-requests/${rid}`,
    { headers: { "X-Requested-With": "RelationshipPlatform" } },
  );
  expect(removed.status()).toBe(204);
  createdRequestId = undefined;
  await page.getByRole("button", { name: "Toggle navigation" }).click();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Welcome back" }),
  ).toBeVisible();
});
