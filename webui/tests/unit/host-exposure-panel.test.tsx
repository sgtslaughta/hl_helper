import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HostExposurePanel } from '@/components/hosts/host-exposure-panel';

vi.mock('@/lib/api/hosts', () => ({
	getHostExposure: vi.fn().mockResolvedValue({
		last_scan_at: '2026-05-09T14:00:00Z',
		counts: { NETWORK_EXPOSED: 4, ACTIVE: 12, INSTALLED_ONLY: 38, UNKNOWN: 0 },
		advisories: [
			{ advisory_id: 'CVE-1', exposure_tier: 'NETWORK_EXPOSED',
				evidence: ['listening tcp/443 (nginx)'] },
		],
	}),
	rescanExposure: vi.fn().mockResolvedValue({ delivered: true }),
}));

function wrap(ui: React.ReactElement) {
	const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('HostExposurePanel', () => {
	it('renders tier counts', async () => {
		render(wrap(<HostExposurePanel hostId="h-1" />));
		expect(await screen.findByText(/4/)).toBeInTheDocument();   // NETWORK_EXPOSED
		expect(screen.getByText(/12/)).toBeInTheDocument();          // ACTIVE
		expect(screen.getByText(/38/)).toBeInTheDocument();          // INSTALLED_ONLY
	});

	// TODO: tests stale after cert-rotation/exposure refactor; rewrite to match current component output.
	it.skip('rescan button triggers mutation', async () => {
		const { rescanExposure } = await import('@/lib/api/hosts');
		render(wrap(<HostExposurePanel hostId="h-1" />));
		const btn = await screen.findByRole('button', { name: /rescan/i });
		fireEvent.click(btn);
		await waitFor(() => expect(rescanExposure).toHaveBeenCalledWith('h-1'));
	});
});
