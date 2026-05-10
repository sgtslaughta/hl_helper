import { describe, it, expect, vi } from 'vitest';
import { listLogs } from '@/lib/api/logs';

vi.mock('@/lib/api-client', () => ({
	apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api-client';

describe('listLogs', () => {
	it('builds query with filters', async () => {
		const fetcher = vi.fn(async () => ({ items: [], next_cursor: null }));
		await listLogs(
			{
				hostId: 'h',
				level: 'warn',
				categories: ['task', 'plugin.*'],
				from: '2026-05-01T00:00:00Z',
				to: '2026-05-02T00:00:00Z',
				q: 'fail',
			},
			fetcher as any,
		);
		expect(fetcher).toHaveBeenCalledTimes(1);
		const url = fetcher.mock.calls[0][0] as string;
		expect(url).toContain('host_id=h');
		expect(url).toContain('level=warn');
		expect(url).toContain('category=task');
		expect(url).toContain('category=plugin.');
		expect(url).toContain('q=fail');
	});

	it('appends multiple host_ids', async () => {
		const fetcher = vi.fn(async () => ({ items: [], next_cursor: null }));
		await listLogs({ hostIds: ['a', 'b'] }, fetcher as any);
		const url = fetcher.mock.calls[0][0] as string;
		expect((url.match(/host_id=/g) || []).length).toBe(2);
		expect(url).toContain('host_id=a');
		expect(url).toContain('host_id=b');
	});

	it('uses default apiFetch when no fetcher provided', async () => {
		(apiFetch as any).mockResolvedValue({ items: [], next_cursor: null });
		await listLogs({ hostId: 'test' });
		expect(apiFetch).toHaveBeenCalled();
		const url = (apiFetch as any).mock.calls[0][0] as string;
		expect(url).toContain('/v1/logs');
		expect(url).toContain('host_id=test');
	});

	it('returns response unchanged', async () => {
		const mockResp = {
			items: [
				{
					id: 1,
					host_id: 'h1',
					agent_id: 'a1',
					agent_session_id: 'sess1',
					seq: 100,
					ts: '2026-05-10T10:00:00Z',
					level: 'info' as const,
					action: 'task.exec.completed',
					category: 'task',
					labels: {},
					details: { rc: 0 },
				},
			],
			next_cursor: 'next-token',
		};
		const fetcher = vi.fn(async () => mockResp);
		const resp = await listLogs({ hostId: 'h1' }, fetcher as any);
		expect(resp).toEqual(mockResp);
	});

	it('handles limit parameter', async () => {
		const fetcher = vi.fn(async () => ({ items: [], next_cursor: null }));
		await listLogs({ limit: 50 }, fetcher as any);
		const url = fetcher.mock.calls[0][0] as string;
		expect(url).toContain('limit=50');
	});

	it('handles cursor parameter', async () => {
		const fetcher = vi.fn(async () => ({ items: [], next_cursor: null }));
		await listLogs({ cursor: 'abc123' }, fetcher as any);
		const url = fetcher.mock.calls[0][0] as string;
		expect(url).toContain('cursor=abc123');
	});

	it('handles outcome filter', async () => {
		const fetcher = vi.fn(async () => ({ items: [], next_cursor: null }));
		await listLogs({ outcome: 'failure' }, fetcher as any);
		const url = fetcher.mock.calls[0][0] as string;
		expect(url).toContain('outcome=failure');
	});

	it('handles action filter', async () => {
		const fetcher = vi.fn(async () => ({ items: [], next_cursor: null }));
		await listLogs({ action: 'task.exec.dispatched' }, fetcher as any);
		const url = fetcher.mock.calls[0][0] as string;
		expect(url).toContain('action=task.exec.dispatched');
	});
});

import { humanize, glyphForOutcome, formatDuration } from '@/lib/event-humanizer';

describe('event-humanizer', () => {
	it('renders action with rc + duration', () => {
		const s = humanize({
			action: 'task.exec.completed',
			outcome: 'success',
			duration_ns: 1_843_000_000,
			details: { rc: 0 },
		});
		expect(s).toMatch(/completed/i);
		expect(s).toContain('1.8s');
	});

	it('glyph maps outcomes', () => {
		expect(glyphForOutcome('success')).toBe('✓');
		expect(glyphForOutcome('failure')).toBe('✗');
		expect(glyphForOutcome('unknown')).toBe('◐');
		expect(glyphForOutcome(undefined)).toBe('◐');
	});

	it('formats sub-second + ms', () => {
		expect(formatDuration(324_000_000)).toBe('324ms');
		expect(formatDuration(1_500_000_000)).toBe('1.5s');
		expect(formatDuration(undefined)).toBe('');
	});

	it('formats durations correctly for various ranges', () => {
		expect(formatDuration(100_000_000)).toBe('100ms');
		expect(formatDuration(1_000_000_000)).toBe('1.0s');
		expect(formatDuration(5_000_000_000)).toBe('5.0s');
		expect(formatDuration(0)).toBe('0ms');
	});

	it('humanize with no details or duration', () => {
		const s = humanize({ action: 'host.enrolled' });
		expect(s).toBeTruthy();
	});

	it('humanize uses message when provided', () => {
		const s = humanize({
			action: 'error.occurred',
			message: 'connection timeout',
		});
		expect(s).toContain('connection timeout');
	});
});
