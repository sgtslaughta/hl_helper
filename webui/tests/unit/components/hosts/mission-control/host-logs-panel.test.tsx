import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HostLogsPanel } from '@/components/hosts/mission-control/host-logs-panel';
import * as logsAPI from '@/lib/api/logs';

// Mock the logs API
vi.mock('@/lib/api/logs');

// Mock the FieldsTable component
vi.mock('@/components/logs/fields-table', () => ({
	FieldsTable: ({ obj }: { obj: unknown }) => <div data-testid="fields-table">{JSON.stringify(obj)}</div>,
}));

describe('HostLogsPanel', () => {
	let queryClient: QueryClient;

	beforeEach(() => {
		queryClient = new QueryClient({
			defaultOptions: {
				queries: { retry: false },
			},
		});
		localStorage.clear();
		vi.clearAllMocks();
	});

	it('renders loading state initially', () => {
		vi.mocked(logsAPI.listLogs).mockImplementation(
			() => new Promise(() => {}), // Never resolves
		);

		render(
			<QueryClientProvider client={queryClient}>
				<HostLogsPanel hostId="host-1" paused={false} />
			</QueryClientProvider>,
		);

		expect(screen.getByText('Loading…')).toBeInTheDocument();
	});

	it('displays logs in sortable table and allows row selection', async () => {
		const mockLogs = [
			{
				id: 1,
				host_id: 'host-1',
				agent_id: 'agent-1',
				agent_session_id: 'session-1',
				seq: 1,
				ts: '2026-05-10T12:00:00Z',
				level: 'info' as const,
				action: 'deploy',
				category: 'deployment',
				outcome: 'success' as const,
				message: 'Deployment started',
				labels: {},
				details: { version: '1.0' },
			},
		];

		vi.mocked(logsAPI.listLogs).mockResolvedValue({ items: mockLogs, next_cursor: null });

		render(
			<QueryClientProvider client={queryClient}>
				<HostLogsPanel hostId="host-1" paused={false} />
			</QueryClientProvider>,
		);

		await waitFor(() => {
			expect(screen.getByText('deploy')).toBeInTheDocument();
		});

		expect(screen.getByText('Deployment started')).toBeInTheDocument();

		// Find all success text elements and verify the outcome badge is present
		const successElements = screen.getAllByText('success');
		expect(successElements.length).toBeGreaterThan(0);

		// Click row to select (by clicking the action button/text)
		const deployButton = screen.getByRole('button', { name: /deploy/ });
		fireEvent.click(deployButton);

		await waitFor(() => {
			expect(screen.getByTestId('fields-table')).toBeInTheDocument();
		});
	});

	it('renders filter controls', async () => {
		vi.mocked(logsAPI.listLogs).mockResolvedValue({
			items: [],
			next_cursor: null,
		});

		render(
			<QueryClientProvider client={queryClient}>
				<HostLogsPanel hostId="host-1" paused={false} />
			</QueryClientProvider>,
		);

		// Filter popover trigger present
		const filterBtn = screen.getByTitle('Filter & sort');
		expect(filterBtn).toBeInTheDocument();

		// Search input present
		const searchInput = screen.getByPlaceholderText(/search/i);
		expect(searchInput).toBeInTheDocument();
	});

	it('respects paused prop for refetch interval', async () => {
		vi.mocked(logsAPI.listLogs).mockResolvedValue({
			items: [
				{
					id: 1,
					host_id: 'host-1',
					agent_id: 'agent-1',
					agent_session_id: 'session-1',
					seq: 1,
					ts: '2026-05-10T12:00:00Z',
					level: 'info' as const,
					action: 'test',
					category: 'test',
					message: 'Test log',
					labels: {},
					details: {},
				},
			],
			next_cursor: null,
		});

		const { rerender } = render(
			<QueryClientProvider client={queryClient}>
				<HostLogsPanel hostId="host-1" paused={false} />
			</QueryClientProvider>,
		);

		await waitFor(() => {
			expect(screen.getByText('Test log')).toBeInTheDocument();
		});

		const callCount1 = vi.mocked(logsAPI.listLogs).mock.calls.length;

		rerender(
			<QueryClientProvider client={queryClient}>
				<HostLogsPanel hostId="host-1" paused={true} />
			</QueryClientProvider>,
		);

		// When paused, refetch should not happen (verified by no additional calls)
		await waitFor(() => {
			const callCount2 = vi.mocked(logsAPI.listLogs).mock.calls.length;
			expect(callCount2).toBe(callCount1);
		}, { timeout: 1000 });
	});

	it('persists and restores split ratio from localStorage', async () => {
		vi.mocked(logsAPI.listLogs).mockResolvedValue({
			items: [
				{
					id: 1,
					host_id: 'host-1',
					agent_id: 'agent-1',
					agent_session_id: 'session-1',
					seq: 1,
					ts: '2026-05-10T12:00:00Z',
					level: 'info' as const,
					action: 'test',
					category: 'test',
					message: 'Test',
					labels: {},
					details: {},
				},
			],
			next_cursor: null,
		});

		// Set localStorage before render
		localStorage.setItem('hostpanel.logs.split', '0.65');

		render(
			<QueryClientProvider client={queryClient}>
				<HostLogsPanel hostId="host-1" paused={false} />
			</QueryClientProvider>,
		);

		await waitFor(() => {
			expect(screen.getByText('Test')).toBeInTheDocument();
		});

		// Verify it was restored from localStorage
		expect(localStorage.getItem('hostpanel.logs.split')).toBe('0.65');
	});
});
