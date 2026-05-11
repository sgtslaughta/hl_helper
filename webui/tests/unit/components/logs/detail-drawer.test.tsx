import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DetailDrawer } from '@/components/logs/detail-drawer';
import { describe, it, expect, vi } from 'vitest';
import type { LogRow } from '@/lib/api/logs';

describe('DetailDrawer', () => {
	const mockRow: LogRow = {
		id: 1,
		host_id: 'host-1',
		agent_id: 'agent-1',
		agent_session_id: 'session-1',
		seq: 1,
		ts: '2026-05-10T12:00:00Z',
		level: 'info',
		action: 'task.exec',
		category: 'task',
		message: 'Task executed successfully',
		labels: { env: 'prod' },
		details: { duration: 1000 },
	};

	it('renders nothing when row is null', () => {
		const onClose = vi.fn();
		const { container } = render(<DetailDrawer row={null} onClose={onClose} />);
		expect(container.firstChild).toBeNull();
	});

	it('renders drawer with row data when row is provided', () => {
		const onClose = vi.fn();
		render(<DetailDrawer row={mockRow} onClose={onClose} />);
		expect(screen.getByText('Log Details')).toBeInTheDocument();
		expect(screen.getByText(/task.exec/)).toBeInTheDocument();
	});

	it('calls onClose when close button is clicked', async () => {
		const onClose = vi.fn();
		render(<DetailDrawer row={mockRow} onClose={onClose} />);
		const user = userEvent.setup();

		const closeButton = screen.getByTitle(/Close/);
		await user.click(closeButton);

		expect(onClose).toHaveBeenCalled();
	});
});
