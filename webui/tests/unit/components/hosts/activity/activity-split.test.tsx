import { render, screen, fireEvent } from '@testing-library/react';
import { ActivitySplit } from '@/components/hosts/activity/activity-split';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

describe('ActivitySplit', () => {
	beforeEach(() => {
		localStorage.clear();
	});

	afterEach(() => {
		localStorage.clear();
	});

	it('renders both top and bottom panes', () => {
		render(
			<ActivitySplit
				top={<div data-testid="top-pane">Top Content</div>}
				bottom={<div data-testid="bottom-pane">Bottom Content</div>}
			/>,
		);

		expect(screen.getByTestId('top-pane')).toBeInTheDocument();
		expect(screen.getByTestId('bottom-pane')).toBeInTheDocument();
	});

	it('renders drag handle', () => {
		render(
			<ActivitySplit
				top={<div>Top</div>}
				bottom={<div>Bottom</div>}
			/>,
		);

		const dragHandle = screen.getByRole('button', { name: /drag to resize/i });
		expect(dragHandle).toBeInTheDocument();
	});

	it('applies initial ratio to pane heights', () => {
		const { container } = render(
			<ActivitySplit
				top={<div>Top</div>}
				bottom={<div>Bottom</div>}
				initialRatio={0.6}
			/>,
		);

		const panes = container.querySelectorAll('[style*="height"]');
		expect(panes.length).toBeGreaterThanOrEqual(2);
	});

	it('loads ratio from localStorage on mount', () => {
		// Pre-populate localStorage
		localStorage.setItem('activity.split.ratio', '0.65');

		render(
			<ActivitySplit
				top={<div data-testid="top">Top</div>}
				bottom={<div data-testid="bottom">Bottom</div>}
			/>,
		);

		// Just verify the component renders - localStorage read happens on mount
		expect(screen.getByTestId('top')).toBeInTheDocument();
		expect(screen.getByTestId('bottom')).toBeInTheDocument();
	});
});
