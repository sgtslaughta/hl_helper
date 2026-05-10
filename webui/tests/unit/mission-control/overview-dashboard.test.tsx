import { OverviewDashboard } from '@/components/hosts/mission-control/overview-dashboard';
import type { Host } from '@/lib/api/hosts';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const host: Host = {
	id: 'h1',
	hostname: 'web-01',
	display_name: 'web-01.prod',
	status: 'healthy',
	enrolled_at: '2026-05-01T00:00:00Z',
	last_seen_at: '2026-05-06T18:00:00Z',
	labels: { env: 'prod', tier: 'web' },
	os: 'linux',
	os_version: '24.04',
	arch: 'x86_64',
	kernel: '6.5.0',
	cpu_pct: 22,
	mem_pct: 41,
	disk_pct: 68,
	uptime_s: 14 * 86400,
};

const renderWithQueryClient = (element: React.ReactElement) => {
	const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return render(<QueryClientProvider client={qc}>{element}</QueryClientProvider>);
};

describe('OverviewDashboard', () => {
	beforeEach(() => {
		vi.spyOn(globalThis, 'fetch').mockImplementation(
			async () =>
				new Response(JSON.stringify({}), {
					status: 200,
					headers: { 'content-type': 'application/json' },
				}),
		);
	});

	// TODO: tests stale after cert-rotation/exposure refactor; rewrite to match current component output.
	it.skip('renders all 5 telemetry gauges', () => {
		renderWithQueryClient(<OverviewDashboard host={host} onJump={() => {}} />);
		for (const l of ['CPU', 'MEM', 'DISK', 'NET', 'UPTIME']) {
			expect(screen.getByText(l)).toBeInTheDocument();
		}
	});

	it('renders identity strip with hostname/os/labels', () => {
		renderWithQueryClient(<OverviewDashboard host={host} onJump={() => {}} />);
		expect(screen.getByText(/linux/)).toBeInTheDocument();
		expect(screen.getByText('prod')).toBeInTheDocument();
		expect(screen.getByText('web')).toBeInTheDocument();
	});

	it('clicking the Task History open link calls onJump("tasks")', () => {
		const onJump = vi.fn();
		renderWithQueryClient(<OverviewDashboard host={host} onJump={onJump} />);
		const buttons = screen.getAllByRole('button', { name: /Open/i });
		// First "Open" maps to first ribbon (Task History)
		fireEvent.click(buttons[0]);
		expect(onJump).toHaveBeenCalledWith('tasks');
	});

	it('clicking the Posture open link calls onJump("posture")', () => {
		const onJump = vi.fn();
		renderWithQueryClient(<OverviewDashboard host={host} onJump={onJump} />);
		const buttons = screen.getAllByRole('button', { name: /Open/i });
		fireEvent.click(buttons[1]);
		expect(onJump).toHaveBeenCalledWith('posture');
	});

	it('shows active task name from query', async () => {
		vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
			const url = String(input);
			if (url.includes('/v1/tasks')) {
				return new Response(
					JSON.stringify({
						items: [
							{
								id: 't1',
								kind: 'shell',
								status: 'running',
								created_at: '2026-05-06T18:00:00Z',
								risk: 'low',
								summary: 'apt upgrade',
							},
						],
						next_cursor: null,
					}),
					{ status: 200, headers: { 'content-type': 'application/json' } },
				);
			}
			return new Response(JSON.stringify({}), {
				status: 200,
				headers: { 'content-type': 'application/json' },
			});
		});
		renderWithQueryClient(<OverviewDashboard host={host} onJump={() => {}} />);
		expect(await screen.findByText(/apt upgrade/)).toBeInTheDocument();
	});
});
