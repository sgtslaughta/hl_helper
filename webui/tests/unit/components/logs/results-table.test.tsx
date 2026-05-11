import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ResultsTable } from '@/components/logs/results-table';
import { describe, it, expect, vi } from 'vitest';
import type { LogRow } from '@/lib/api/logs';

describe('ResultsTable', () => {
	const mockRows: LogRow[] = [
		{
			id: 1,
			host_id: 'host-1',
			agent_id: 'agent-1',
			agent_session_id: 'session-1',
			seq: 1,
			ts: '2026-05-10T12:00:00Z',
			level: 'info',
			action: 'task.start',
			category: 'task',
			message: 'Starting task',
			labels: {},
			details: {},
		},
		{
			id: 2,
			host_id: 'host-2',
			agent_id: 'agent-2',
			agent_session_id: 'session-2',
			seq: 2,
			ts: '2026-05-10T12:01:00Z',
			level: 'error',
			action: 'task.fail',
			category: 'task',
			outcome: 'failure',
			message: 'Task failed',
			labels: {},
			details: {},
		},
	];

	it('renders table headers', () => {
		render(<ResultsTable rows={mockRows} />);
		expect(screen.getByText('Timestamp')).toBeInTheDocument();
		expect(screen.getByText('Host')).toBeInTheDocument();
		expect(screen.getByText('Level')).toBeInTheDocument();
		expect(screen.getByText('Action')).toBeInTheDocument();
	});

	it('renders rows with correct data', () => {
		render(<ResultsTable rows={mockRows} />);
		expect(screen.getByText('host-1')).toBeInTheDocument();
		expect(screen.getByText('task.start')).toBeInTheDocument();
		expect(screen.getByText('host-2')).toBeInTheDocument();
		expect(screen.getByText('task.fail')).toBeInTheDocument();
	});

	it('calls onRowClick when row is clicked', async () => {
		const onRowClick = vi.fn();
		render(<ResultsTable rows={mockRows} onRowClick={onRowClick} />);
		const user = userEvent.setup();

		const row = screen.getByText('task.start').closest('tr');
		if (row) await user.click(row);

		expect(onRowClick).toHaveBeenCalledWith(expect.objectContaining({ action: 'task.start' }));
	});
});
