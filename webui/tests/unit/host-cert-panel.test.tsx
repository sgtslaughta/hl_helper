import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HostCertPanel } from '@/components/hosts/host-cert-panel';

vi.mock('@/lib/api/hosts', () => ({
	getHostCert: vi.fn().mockResolvedValue({
		serial: 'ABCD1234EF',
		issued_at: '2026-05-08T12:00:00Z',
		expires_at: '2026-05-15T12:00:00Z',
		rotation_count: 3,
		last_rotated_at: '2026-05-09T12:00:00Z',
		last_reenroll_at: null,
		status: 'healthy',
	}),
	rotateCertNow: vi.fn(),
	mintReenrollToken: vi.fn(),
}));

function wrap(ui: React.ReactElement) {
	const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('HostCertPanel', () => {
	it('renders serial + status + rotation count', async () => {
		render(wrap(<HostCertPanel hostId="h-1" />));
		expect(await screen.findByText(/ABCD1234.*EF/)).toBeInTheDocument();
		expect(screen.getByText(/Healthy/i)).toBeInTheDocument();
		expect(screen.getByText(/3×/)).toBeInTheDocument();
	});

	it('shows force rotate + reenroll buttons', async () => {
		render(wrap(<HostCertPanel hostId="h-1" />));
		expect(await screen.findByRole('button', { name: /force rotate/i })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /re-enroll/i })).toBeInTheDocument();
	});
});
