import { TopBar } from '@/components/hosts/mission-control/top-bar';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/rbac', () => ({
	useCanPerform: () => ({ allowed: true, reason: '', principal: 'u' }),
}));

function wrap(ui: ReactNode) {
	const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('TopBar', () => {
	it('renders status pips for non-zero counts only', () => {
		render(
			wrap(
				<TopBar counts={{ critical: 2, pending: 1, online: 14, offline: 0 }} onEnroll={() => {}} />,
			),
		);
		expect(screen.getByText('CRIT')).toBeInTheDocument();
		expect(screen.getByText('PEND')).toBeInTheDocument();
		expect(screen.getByText('ONLINE')).toBeInTheDocument();
		expect(screen.queryByText('OFFLINE')).toBeNull();
	});

	it('clicking a status pip calls onPillClick', () => {
		const onPillClick = vi.fn();
		render(
			wrap(
				<TopBar
					counts={{ critical: 2, pending: 0, online: 0, offline: 0 }}
					onEnroll={() => {}}
					onPillClick={onPillClick}
				/>,
			),
		);
		fireEvent.click(screen.getByText('CRIT'));
		expect(onPillClick).toHaveBeenCalledWith('critical');
	});

	it('Enroll button calls onEnroll when clicked (RBAC allowed)', () => {
		const onEnroll = vi.fn();
		render(
			wrap(
				<TopBar counts={{ critical: 0, pending: 0, online: 0, offline: 0 }} onEnroll={onEnroll} />,
			),
		);
		fireEvent.click(screen.getByRole('button', { name: /Enroll Host/i }));
		expect(onEnroll).toHaveBeenCalled();
	});
});
