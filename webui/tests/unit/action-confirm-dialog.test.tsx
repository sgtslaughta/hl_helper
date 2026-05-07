import { ActionConfirmDialog } from '@/components/hosts/action-confirm-dialog';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/auth', () => ({
	useAuth: () => ({
		user: { id: 'u1', email: 'admin@example.com', username: 'admin', roles: ['admin'], groups: [] },
		authenticated: true,
		isLoading: false,
	}),
}));

const HOST = { id: 'h1', hostname: 'lab-router-01' };

function wrap(ui: ReactNode) {
	const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('ActionConfirmDialog', () => {
	it('renders summary and risks for action', async () => {
		render(
			wrap(
				<ActionConfirmDialog
					action="reboot"
					host={HOST}
					principal="u1"
					onConfirm={vi.fn()}
					onClose={vi.fn()}
				/>,
			),
		);
		expect(screen.getByText(/Reboot host/i)).toBeInTheDocument();
		// Summary types out via animation; wait for completion.
		expect(await screen.findByText(/Restarts the host/i)).toBeInTheDocument();
		// Cautions panel is collapsed by default — expand it.
		fireEvent.click(screen.getByRole('button', { name: /Cautions/i }));
		expect(screen.getByText(/Active sessions/i)).toBeInTheDocument();
	});

	it('disables confirm until hostname typed for irreversible', () => {
		render(
			wrap(
				<ActionConfirmDialog
					action="revoke-host"
					host={HOST}
					principal="u1"
					onConfirm={vi.fn()}
					onClose={vi.fn()}
				/>,
			),
		);
		const confirm = screen.getByRole('button', { name: /confirm/i });
		expect(confirm).toBeDisabled();
		fireEvent.change(screen.getByRole('textbox'), { target: { value: 'lab-router-01' } });
		expect(confirm).toBeEnabled();
	});

	it('calls onConfirm when clicked for non-irreversible', () => {
		const onConfirm = vi.fn();
		render(
			wrap(
				<ActionConfirmDialog
					action="reboot"
					host={HOST}
					principal="u1"
					onConfirm={onConfirm}
					onClose={vi.fn()}
				/>,
			),
		);
		fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
		expect(onConfirm).toHaveBeenCalled();
	});

	it('renders custom form between risks and disclosures', () => {
		render(
			wrap(
				<ActionConfirmDialog
					action="shell-exec"
					host={HOST}
					principal="u1"
					onConfirm={vi.fn()}
					onClose={vi.fn()}
					formChildren={<input data-testid="cmd" placeholder="cmd" />}
				/>,
			),
		);
		expect(screen.getByTestId('cmd')).toBeInTheDocument();
	});

	it('shows display name from auth, not principal id', () => {
		render(
			wrap(
				<ActionConfirmDialog
					action="reboot"
					host={HOST}
					principal="u1"
					onConfirm={vi.fn()}
					onClose={vi.fn()}
				/>,
			),
		);
		expect(screen.getByText('admin')).toBeInTheDocument();
	});
});
