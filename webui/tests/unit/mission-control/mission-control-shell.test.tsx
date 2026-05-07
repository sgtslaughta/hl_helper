import { MissionControlShell } from '@/components/hosts/mission-control/mission-control-shell';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
	useRouter: () => ({ replace: vi.fn() }),
	usePathname: () => '/hosts',
	useParams: () => ({}),
}));

vi.mock('@/lib/api/hosts', async () => {
	const actual = await vi.importActual<typeof import('@/lib/api/hosts')>('@/lib/api/hosts');
	return {
		...actual,
		listHosts: vi.fn(async () => [
			{
				id: 'h1',
				hostname: 'a',
				display_name: null,
				status: 'healthy',
				enrolled_at: '',
				last_seen_at: null,
				labels: {},
			},
		]),
		getHost: vi.fn(async () => ({
			id: 'h1',
			hostname: 'a',
			display_name: null,
			status: 'healthy',
			enrolled_at: '',
			last_seen_at: null,
			labels: {},
		})),
	};
});

vi.mock('@/lib/api/enrollment', () => ({
	listPendingTokens: vi.fn(async () => []),
}));

vi.mock('@/lib/rbac', () => ({
	useCanPerform: () => ({ allowed: true, reason: '', principal: 'u' }),
}));

vi.mock('@/components/hosts/host-terminal-panel', () => ({
	HostTerminalPanel: () => <div>terminal-panel</div>,
}));

vi.mock('@/components/hosts/host-posture-panel', () => ({
	HostPosturePanel: () => <div>posture-panel</div>,
}));
vi.mock('@/components/hosts/host-audit-panel', () => ({
	HostAuditPanel: () => <div>audit-panel</div>,
}));
vi.mock('@/components/hosts/host-tasks-panel', () => ({
	HostTasksPanel: () => <div>tasks-panel</div>,
}));

function wrap(ui: React.ReactElement) {
	const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('MissionControlShell', () => {
	it('renders top bar, fleet rail, and an empty-state when no host selected', async () => {
		render(wrap(<MissionControlShell initialHostId={null} />));
		expect(await screen.findByRole('listbox', { name: /Fleet/ })).toBeInTheDocument();
		expect(screen.getByText(/select a host/i)).toBeInTheDocument();
	});

	it('focus tab key 1 switches focus pane to Posture', async () => {
		render(wrap(<MissionControlShell initialHostId="h1" />));
		await screen.findByRole('tab', { name: /Posture/ });
		fireEvent.keyDown(window, { key: '1' });
		expect(await screen.findByRole('tab', { name: /Posture/ })).toHaveAttribute(
			'aria-selected',
			'true',
		);
	});

	it('action key e switches action pane to Logs', async () => {
		render(wrap(<MissionControlShell initialHostId="h1" />));
		await screen.findByRole('tab', { name: /Terminal/ });
		fireEvent.keyDown(window, { key: 'e' });
		expect(await screen.findByRole('tab', { name: /Logs/ })).toHaveAttribute(
			'aria-selected',
			'true',
		);
	});

	it.todo('resets focus mode to overview when host changes');
});
