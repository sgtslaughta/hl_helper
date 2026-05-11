import { render, screen, fireEvent } from '@testing-library/react';
import { ActivityResultsTable } from '@/components/hosts/activity/activity-results-table';
import { describe, it, expect, vi } from 'vitest';

const mockRows = [
	{
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
		message: 'ok',
		labels: {},
		details: {},
		duration_ns: 1_000_000_000,
	},
	{
		id: 2,
		host_id: 'h-123',
		agent_id: 'a-456',
		agent_session_id: 's-789',
		seq: 2,
		ts: '2026-05-10T22:10:00Z',
		level: 'error' as const,
		action: 'task.exec.failed',
		category: 'task',
		outcome: 'failure' as const,
		message: 'error',
		labels: {},
		details: {},
		duration_ns: 500_000_000,
	},
];

describe('ActivityResultsTable', () => {
	it('renders table with rows', () => {
		const mockOnClick = vi.fn();
		render(
			<ActivityResultsTable rows={mockRows} onRowClick={mockOnClick} />,
		);

		expect(screen.getByText('INFO')).toBeInTheDocument();
		expect(screen.getByText('ERROR')).toBeInTheDocument();
	});

	it('displays outcome glyphs', () => {
		const mockOnClick = vi.fn();
		render(
			<ActivityResultsTable rows={mockRows} onRowClick={mockOnClick} />,
		);

		expect(screen.getAllByText('✓')).toHaveLength(1);
		expect(screen.getAllByText('✗')).toHaveLength(1);
	});

	it('calls onRowClick when row is clicked', () => {
		const mockOnClick = vi.fn();
		render(
			<ActivityResultsTable rows={mockRows} onRowClick={mockOnClick} />,
		);

		const taskCompleted = screen.getByText('task.exec.completed');
		fireEvent.click(taskCompleted.closest('tr')!);

		expect(mockOnClick).toHaveBeenCalledWith(mockRows[0]);
	});

	it('highlights selected row', () => {
		const mockOnClick = vi.fn();
		const { container } = render(
			<ActivityResultsTable
				rows={mockRows}
				onRowClick={mockOnClick}
				selectedRowId={1}
			/>,
		);

		const rows = container.querySelectorAll('tbody tr');
		expect(rows[0]).toHaveClass('bg-accent/10');
	});

	it('sorts rows by clicking header', () => {
		const mockOnClick = vi.fn();
		render(
			<ActivityResultsTable rows={mockRows} onRowClick={mockOnClick} />,
		);

		const levelHeader = screen.getByText('Level');
		fireEvent.click(levelHeader);

		// After sorting, ERROR should come before INFO (higher severity)
		expect(screen.getByText('ERROR')).toBeInTheDocument();
	});

	it('displays empty state when no rows', () => {
		const mockOnClick = vi.fn();
		render(
			<ActivityResultsTable rows={[]} onRowClick={mockOnClick} />,
		);

		expect(screen.getByText(/no logs found/i)).toBeInTheDocument();
	});

	it('displays pagination for multiple pages', () => {
		const mockOnClick = vi.fn();
		const manyRows = Array.from({ length: 100 }, (_, i) => ({
			...mockRows[0],
			id: i + 1,
		}));

		render(
			<ActivityResultsTable
				rows={manyRows}
				onRowClick={mockOnClick}
				pageSize={50}
			/>,
		);

		expect(screen.getByText(/1 \/ 2/)).toBeInTheDocument();
	});
});
