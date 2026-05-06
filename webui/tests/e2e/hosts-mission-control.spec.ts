import { test, expect } from '@playwright/test';

test.describe('Hosts mission control', () => {
  test('keyboard switches focus pane tabs 1-4', async ({ page }) => {
    await page.goto('/hosts');
    const firstHost = page.locator('[role=option]').first();
    await firstHost.waitFor({ state: 'visible' });
    await firstHost.click();
    await page.keyboard.press('2');
    await expect(page.getByRole('tab', { name: /Posture/ })).toHaveAttribute('aria-selected', 'true');
    await page.keyboard.press('3');
    await expect(page.getByRole('tab', { name: /Audit/ })).toHaveAttribute('aria-selected', 'true');
  });

  test('action pane runs independently of focus pane', async ({ page }) => {
    await page.goto('/hosts');
    const firstHost = page.locator('[role=option]').first();
    await firstHost.waitFor({ state: 'visible' });
    await firstHost.click();
    await page.keyboard.press('1');
    await page.keyboard.press('w');
    await expect(page.getByRole('tab', { name: /Overview/ })).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByRole('tab', { name: /Terminal/ })).toHaveAttribute('aria-selected', 'true');
  });

  test('density toggle cycles', async ({ page }) => {
    await page.goto('/hosts');
    const btn = page.getByRole('button', { name: /Density:/ });
    await btn.waitFor({ state: 'visible' });
    const before = await btn.getAttribute('aria-label');
    await btn.click();
    const after = await btn.getAttribute('aria-label');
    expect(before).not.toBe(after);
  });

  test('deep link /hosts/<id> hydrates selection', async ({ page }) => {
    await page.goto('/hosts');
    const first = page.locator('[role=option]').first();
    await first.waitFor({ state: 'visible' });
    await first.click();
    await page.waitForURL(/\/hosts\/[^/]+/);
    const url = page.url();
    await page.goto(url);
    await expect(page.locator('[role=option][aria-selected=true]')).toHaveCount(1);
  });
});
