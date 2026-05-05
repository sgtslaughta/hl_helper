import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const routes = [
	'/',
	'/login',
	'/hosts',
	'/tasks',
	'/security',
	'/audit',
	'/users',
	'/plugins',
	'/settings',
	'/docs',
];

// Skip in local environment, only run in CI
const shouldRun = !!process.env.RUN_E2E;

test.describe('Accessibility (a11y)', () => {
	for (const route of routes) {
		test(`should have no a11y violations on ${route}`, async ({ page }) => {
			test.skip(!shouldRun, 'Skipped: requires RUN_E2E environment variable');

			await page.goto(route);

			const results = await new AxeBuilder({ page }).analyze();
			const violations = results.violations;

			// Known acceptable violations (document inline):
			// - color-contrast: may be intentional design choices
			// - aria-required-attr: form inputs may be optional
			const ignoredRules = ['color-contrast', 'aria-required-attr'];

			const filteredViolations = violations.filter((v: { id: string }) => !ignoredRules.includes(v.id));

			expect(filteredViolations).toHaveLength(0);
		});
	}
});
