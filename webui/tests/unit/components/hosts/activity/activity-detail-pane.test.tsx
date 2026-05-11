import { render, screen } from '@testing-library/react';
import { ActivityDetailPane } from '@/components/hosts/activity/activity-detail-pane';
import { describe, it, expect } from 'vitest';

const mockRow = {
	id: 1,
	host_id: 'h-123',
	agent_id: 'a-456',
	agent_session_id: 's-789',
	seq: 1,
	ts: '2026-05-10T22:15:03Z',
	level: 'info' as const,
	action: 'task.exec.completed',
	category: 'task',
	outcome: 'success' as const,
	message: 'completed successfully',
	labels: {},
	details: { rc: 0 },
	duration_ns: 1_000_000_000,
};

describe('ActivityDetailPane', () => {
	it('displays empty state when row is null', () => {
		render(<ActivityDetailPane row={null} />);
		expect(screen.getByText(/select a row to inspect/i)).toBeInTheDocument();
	});

	it('renders row header with action and outcome glyph', () => {
		const { container } = render(<ActivityDetailPane row={mockRow} />);
		expect(screen.getByText('✓')).toBeInTheDocument();
		// Check for the action in the header (first occurrence of 'completed')
		const header = container.querySelector('.border-b.border-hairline');
		expect(header?.textContent).toContain('completed');
	});

	it('displays level badge', () => {
		render(<ActivityDetailPane row={mockRow} />);
		expect(screen.getByText('INFO')).toBeInTheDocument();
	});

	it('displays agent session id chip', () => {
		const { container } = render(<ActivityDetailPane row={mockRow} />);
		// Find the session chip div (the one that's not in the table)
		const sessionChip = container.querySelector('.bg-surface.border.border-hairline.text-text-dim.font-mono');
		expect(sessionChip?.textContent).toContain('s-789');
	});

	it('renders copy buttons', () => {
		render(<ActivityDetailPane row={mockRow} />);
		expect(screen.getByText('Copy fields')).toBeInTheDocument();
		expect(screen.getByText('Copy JSON')).toBeInTheDocument();
	});

	it('displays duration when present', () => {
		const rowWithDuration = { ...mockRow, duration_ns: 2_500_000_000 };
		render(<ActivityDetailPane row={rowWithDuration} />);
		expect(screen.getByText(/2\.5s/)).toBeInTheDocument();
	});

	it('renders FieldsTable for row object', () => {
		render(<ActivityDetailPane row={mockRow} />);
		// FieldsTable should render and flatten the row object
		const table = screen.getByRole('table');
		expect(table).toBeInTheDocument();
	});
});
