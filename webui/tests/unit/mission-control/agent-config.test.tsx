import { AgentConfig } from '@/components/hosts/mission-control/agent-config';
import type { Host } from '@/lib/api/hosts';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api/hosts', () => ({
	updateHeartbeatInterval: vi.fn(),
	deleteHost: vi.fn(),
	rebootHost: vi.fn(),
	shellExecHost: vi.fn(),
	pkgUpdateHost: vi.fn(),
	revokeHostCert: vi.fn(),
	listHosts: vi.fn(),
	getHost: vi.fn(),
	pruneStaleHosts: vi.fn(),
	resurveyHost: vi.fn(),
}));

import { updateHeartbeatInterval } from '@/lib/api/hosts';

const baseHost: Host = {
	id: 'h1',
	hostname: 'web-01',
	display_name: null,
	status: 'healthy',
	enrolled_at: '2026-05-01T00:00:00Z',
	last_seen_at: null,
	labels: {},
	heartbeat_interval_s: 60,
};

function wrap(ui: React.ReactElement) {
	const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('AgentConfig', () => {
	beforeEach(() => vi.clearAllMocks());

	it('renders input with current heartbeat interval', () => {
		render(wrap(<AgentConfig host={baseHost} />));
		const input = screen.getByDisplayValue('60') as HTMLInputElement;
		expect(input).toBeInTheDocument();
	});

	it('enforces min/max range 5-3600', () => {
		render(wrap(<AgentConfig host={baseHost} />));
		const input = screen.getByDisplayValue('60') as HTMLInputElement;
		expect(input).toHaveAttribute('min', '5');
		expect(input).toHaveAttribute('max', '3600');
	});

	it('disables Save button when value < 5', () => {
		render(wrap(<AgentConfig host={baseHost} />));
		const input = screen.getByDisplayValue('60') as HTMLInputElement;
		fireEvent.change(input, { target: { value: '4' } });
		expect(screen.getByRole('button', { name: /Save/i })).toBeDisabled();
	});

	it('disables Save button when value > 3600', () => {
		render(wrap(<AgentConfig host={baseHost} />));
		const input = screen.getByDisplayValue('60') as HTMLInputElement;
		fireEvent.change(input, { target: { value: '3601' } });
		expect(screen.getByRole('button', { name: /Save/i })).toBeDisabled();
	});

	it('calls API when Save clicked with valid value', async () => {
		(updateHeartbeatInterval as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({
			...baseHost,
			heartbeat_interval_s: 120,
		});
		render(wrap(<AgentConfig host={baseHost} />));
		const input = screen.getByDisplayValue('60') as HTMLInputElement;
		fireEvent.change(input, { target: { value: '120' } });
		fireEvent.click(screen.getByRole('button', { name: /Save/i }));
		await waitFor(() =>
			expect(updateHeartbeatInterval).toHaveBeenCalledWith('h1', 120)
		);
	});

	it('shows "Saved" confirmation temporarily after successful update', async () => {
		(updateHeartbeatInterval as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({
			...baseHost,
			heartbeat_interval_s: 120,
		});
		render(wrap(<AgentConfig host={baseHost} />));
		const input = screen.getByDisplayValue('60') as HTMLInputElement;
		fireEvent.change(input, { target: { value: '120' } });
		fireEvent.click(screen.getByRole('button', { name: /Save/i }));
		await waitFor(() => expect(screen.getByText(/Saved/)).toBeInTheDocument());
	});
});
