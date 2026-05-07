import { QuickActions } from '@/components/hosts/mission-control/quick-actions';
import type { Host } from '@/lib/api/hosts';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const host: Host = {
	id: 'h1',
	hostname: 'web-01',
	display_name: null,
	status: 'healthy',
	enrolled_at: '2026-05-01T00:00:00Z',
	last_seen_at: null,
	labels: {},
};

vi.mock('@/lib/api/hosts', () => ({
	resurveyHost: vi.fn(),
	updateHeartbeatInterval: vi.fn(),
	deleteHost: vi.fn(),
	rebootHost: vi.fn(),
	shellExecHost: vi.fn(),
	pkgUpdateHost: vi.fn(),
	revokeHostCert: vi.fn(),
	listHosts: vi.fn(),
	getHost: vi.fn(),
	pruneStaleHosts: vi.fn(),
}));

vi.mock('@/lib/rbac', () => ({
	useCanPerform: (action: string) => ({
		allowed: action !== 'revoke-host',
		reason: action === 'revoke-host' ? 'denied for tests' : '',
		principal: 'u',
	}),
}));

vi.mock('@/lib/auth', () => ({
	useAuth: () => ({
		user: { id: 'u', email: 'admin@example.com', username: 'admin', roles: ['admin'], groups: [] },
		authenticated: true,
		isLoading: false,
	}),
}));

vi.mock('next/navigation', () => ({
	useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
	usePathname: () => '/hosts',
	useParams: () => ({}),
}));

function wrap(ui: React.ReactElement) {
	const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('QuickActions', () => {
	it('renders all 6 supported mission-command actions', () => {
		render(wrap(<QuickActions host={host} />));
		for (const label of [
			'Power Cycle',
			'Shell Command',
			'Package Update',
			'Resurvey',
			'Revoke Trust',
			'Delete Host',
		]) {
			expect(screen.getByRole('button', { name: new RegExp(label, 'i') })).toBeInTheDocument();
		}
	});

	it('disables an RBAC-denied action and surfaces reason in tooltip', () => {
		render(wrap(<QuickActions host={host} />));
		const revoke = screen.getByRole('button', { name: /Revoke Trust/i });
		expect(revoke).toBeDisabled();
		expect(revoke).toHaveAttribute('title', expect.stringMatching(/denied/));
	});

	it('clicking an allowed action opens confirm dialog', () => {
		render(wrap(<QuickActions host={host} />));
		fireEvent.click(screen.getByRole('button', { name: /Power Cycle/i }));
		expect(screen.getByRole('dialog')).toBeInTheDocument();
	});

	it('Resurvey button is enabled and clickable', () => {
		render(wrap(<QuickActions host={host} />));
		const resurveyBtn = screen.getByRole('button', { name: /Resurvey/i });
		expect(resurveyBtn).not.toBeDisabled();
		fireEvent.click(resurveyBtn);
		expect(screen.getByRole('dialog')).toBeInTheDocument();
	});
});
