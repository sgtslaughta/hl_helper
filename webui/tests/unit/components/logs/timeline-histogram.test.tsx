import { render, screen } from '@testing-library/react';
import { TimelineHistogram } from '@/components/logs/timeline-histogram';
import { describe, it, expect } from 'vitest';

describe('TimelineHistogram', () => {
	it('renders empty state when bins is empty', () => {
		render(<TimelineHistogram bins={[]} />);
		expect(screen.getByText('No data')).toBeInTheDocument();
	});

	it('renders histogram bars when bins have data', () => {
		const bins = [
			{ total: 10, errors: 2 },
			{ total: 20, errors: 5 },
			{ total: 15, errors: 0 },
		];
		const { container } = render(<TimelineHistogram bins={bins} />);

		const bars = container.querySelectorAll('[style*="height"]');
		expect(bars.length).toBeGreaterThan(0);
	});

	it('shows error portion when errors present', () => {
		const bins = [{ total: 100, errors: 25 }];
		const { container } = render(<TimelineHistogram bins={bins} />);

		const errorBar = container.querySelector('.bg-danger');
		expect(errorBar).toBeInTheDocument();
	});
});
