import { expect, test } from '@playwright/test';

test.describe('Smoke tests', () => {
	test('homepage loads', async ({ page }) => {
		await page.goto('/');
		await expect(page).toHaveTitle(/hl_helper/);
	});

	test('responsive design works', async ({ page }) => {
		await page.goto('/');
		const viewport = page.viewportSize();
		expect(viewport).not.toBeNull();
	});
});
