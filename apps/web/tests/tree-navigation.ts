import { expect, type Page } from "@playwright/test";

export async function expandProjectTree(page: Page): Promise<void> {
  const toggle = page.locator(".project-row.active .project-folder-toggle");
  await expect(toggle).toBeVisible();
  if (await toggle.getAttribute("aria-expanded") === "false") await toggle.click();
}

export async function expandWorkspace(page: Page, code: string): Promise<void> {
  const node = page.locator(".workspace-node").filter({ has: page.locator(".workspace-row strong", { hasText: code }) });
  const toggle = node.locator(".tree-toggle");
  await expect(toggle).toBeVisible();
  if (await toggle.getAttribute("aria-expanded") === "false") await toggle.click();
}
