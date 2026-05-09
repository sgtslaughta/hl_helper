import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReenrollModal } from '@/components/hosts/reenroll-modal';

vi.mock('@/lib/api/hosts', () => ({
	mintReenrollToken: vi.fn().mockResolvedValue({
		token_id: 't1',
		token: 'hlb_xyz',
		expires_at: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
		install_command: 'sudo hl-agent reenroll --url X --token hlb_xyz',
	}),
}));

function wrap(ui: React.ReactElement) {
	const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('ReenrollModal', () => {
	it('mints token on click and shows install command', async () => {
		render(wrap(<ReenrollModal hostId="h-1" onClose={() => {}} />));
		fireEvent.click(screen.getByRole('button', { name: /mint re-enrollment token/i }));
		await waitFor(() =>
			expect(screen.getByText(/sudo hl-agent reenroll/)).toBeInTheDocument()
		);
	});

	it('copies command via clipboard', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.assign(navigator, { clipboard: { writeText } });
		render(wrap(<ReenrollModal hostId="h-1" onClose={() => {}} />));
		fireEvent.click(screen.getByRole('button', { name: /mint re-enrollment token/i }));
		await waitFor(() => screen.getByText(/sudo hl-agent reenroll/));
		fireEvent.click(screen.getByRole('button', { name: /copy command/i }));
		await waitFor(() => expect(writeText).toHaveBeenCalled());
	});
});
