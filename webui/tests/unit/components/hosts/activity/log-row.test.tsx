import { render, screen } from '@testing-library/react';
import { LogRow } from '@/components/hosts/activity/log-row';
import { describe, it, expect } from 'vitest';

describe('LogRow', () => {
	it('renders action humanized with outcome glyph', () => {
		const row = {
			id: 1,
			host_id: 'h',
			agent_id: 'a',
			agent_session_id: 's',
			seq: 1,
			ts: '2026-05-10T22:15:03Z',
			level: 'info' as const,
			action: 'task.exec.completed',
			category: 'task',
			outcome: 'success' as const,
			message: 'ok',
			labels: {},
			details: { rc: 0 },
			duration_ns: 1_843_000_000,
		};
		render(<LogRow row={row} />);
		expect(screen.getByText(/completed/i)).toBeInTheDocument();
		expect(screen.getByText('✓')).toBeInTheDocument();
		expect(screen.getByText(/1\.8s/)).toBeInTheDocument();
	});

	it('expands JSON on click', async () => {
		const row = {
			id: 1,
			host_id: 'h',
			agent_id: 'a',
			agent_session_id: 's',
			seq: 1,
			ts: '2026-05-10T22:15:03Z',
			level: 'error' as const,
			action: 'task.exec.failed',
			category: 'task',
			outcome: 'failure' as const,
			message: 'error occurred',
			labels: {},
			details: { rc: 1, stderr: 'bad' },
			duration_ns: 500_000_000,
		};
		const { container } = render(<LogRow row={row} />);
		const expandButton = container.querySelector('[data-testid="expand-button"]');
		expect(expandButton).toBeInTheDocument();
	});

	it('displays relative time with absolute on hover title', () => {
		const row = {
			id: 1,
			host_id: 'h',
			agent_id: 'a',
			agent_session_id: 's',
			seq: 1,
			ts: '2026-05-10T22:15:03Z',
			level: 'info' as const,
			action: 'host.enrolled',
			category: 'host',
			outcome: undefined,
			message: undefined,
			labels: {},
			details: {},
		};
		render(<LogRow row={row} />);
		const timeEl = screen.getByText(/ago/i);
		expect(timeEl).toHaveAttribute('title');
		expect(timeEl.getAttribute('title')).toContain('2026-05-10');
	});

	it('renders level badge', () => {
		const row = {
			id: 1,
			host_id: 'h',
			agent_id: 'a',
			agent_session_id: 's',
			seq: 1,
			ts: '2026-05-10T22:15:03Z',
			level: 'warn' as const,
			action: 'some.action',
			category: 'test',
			outcome: undefined,
			message: undefined,
			labels: {},
			details: {},
		};
		render(<LogRow row={row} />);
		expect(screen.getByText('WARN')).toBeInTheDocument();
	});
});
