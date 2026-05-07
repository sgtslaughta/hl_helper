import { FleetRail } from '@/components/hosts/mission-control/fleet-rail';
import type { Host } from '@/lib/api/hosts';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api/hosts', () => ({
	listHosts: vi.fn(
		async () =>
			[
				{
					id: '1',
					hostname: 'a',
					display_name: null,
					status: 'critical',
					enrolled_at: '',
					last_seen_at: null,
					labels: {},
					os: 'linux',
				},
				{
					id: '2',
					hostname: 'b',
					display_name: null,
					status: 'healthy',
					enrolled_at: '',
					last_seen_at: null,
					labels: {},
					os: 'linux',
				},
				{
					id: '3',
					hostname: 'c',
					display_name: null,
					status: 'offline',
					enrolled_at: '',
					last_seen_at: null,
					labels: {},
					os: 'linux',
				},
			] as Host[],
	),
}));
vi.mock('@/lib/api/enrollment', () => ({
	listPendingTokens: vi.fn(async () => []),
}));

function wrap(ui: React.ReactElement) {
	const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('FleetRail', () => {
	beforeEach(() => {
		localStorage.clear();
	});

	it('renders hosts grouped by health with counts', async () => {
		render(wrap(<FleetRail selectedId={null} onSelect={() => {}} />));
		expect(await screen.findByText(/Critical · 1/)).toBeInTheDocument();
		expect(await screen.findByText(/Online · 1/)).toBeInTheDocument();
		expect(await screen.findByText(/Offline · 1/)).toBeInTheDocument();
	});

	it('selecting a row fires onSelect with host id', async () => {
		const onSelect = vi.fn();
		render(wrap(<FleetRail selectedId={null} onSelect={onSelect} />));
		const row = await screen.findByText('a');
		fireEvent.click(row);
		expect(onSelect).toHaveBeenCalledWith('1');
	});

	it('density button toggles aria-label', async () => {
		render(wrap(<FleetRail selectedId={null} onSelect={() => {}} />));
		const btn = await screen.findByLabelText(/Density: balanced/i);
		fireEvent.click(btn);
		expect(await screen.findByLabelText(/Density: rich/i)).toBeInTheDocument();
	});
});
