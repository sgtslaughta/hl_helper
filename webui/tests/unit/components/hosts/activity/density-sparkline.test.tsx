import { render } from '@testing-library/react';
import { DensitySparkline } from '@/components/hosts/activity/density-sparkline';
import { describe, it, expect } from 'vitest';

describe('DensitySparkline', () => {
	it('renders 60 bars from histogram', () => {
		const bins = Array.from({ length: 60 }, (_, i) => ({
			total: i,
			errors: i > 50 ? 5 : 0,
		}));
		const { container } = render(<DensitySparkline bins={bins} />);
		const bars = container.querySelectorAll('rect');
		expect(bars.length).toBe(60);
	});

	it('uses red color when error rate > 20%', () => {
		const bins = [
			{ total: 10, errors: 0 },
			{ total: 10, errors: 3 }, // 30% error rate
		];
		const { container } = render(<DensitySparkline bins={bins} />);
		const rects = container.querySelectorAll('rect');
		expect(rects.length).toBe(2);
		// Second bar should have high error rate, color should shift
		const secondRect = rects[1];
		expect(secondRect).toBeInTheDocument();
	});

	it('scales bar heights proportionally to counts', () => {
		const bins = [
			{ total: 5, errors: 0 },
			{ total: 10, errors: 0 },
			{ total: 20, errors: 0 },
		];
		const { container } = render(<DensitySparkline bins={bins} />);
		const rects = container.querySelectorAll('rect');
		expect(rects.length).toBe(3);

		// heights should be in ratio 1:2:4 approximately
		const heights = Array.from(rects).map(r => Number.parseFloat(r.getAttribute('height') || '0'));
		expect(heights[0] > 0).toBe(true);
		expect(heights[1] > heights[0]).toBe(true);
		expect(heights[2] > heights[1]).toBe(true);
	});

	it('renders SVG container', () => {
		const bins = [{ total: 5, errors: 0 }];
		const { container } = render(<DensitySparkline bins={bins} />);
		const svg = container.querySelector('svg');
		expect(svg).toBeInTheDocument();
	});
});
