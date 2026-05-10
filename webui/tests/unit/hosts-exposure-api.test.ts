import { describe, it, expect, vi } from 'vitest';
import { getHostExposure, rescanExposure } from '@/lib/api/hosts';

vi.mock('@/lib/api-client', () => ({
	apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api-client';

describe('hosts exposure API', () => {
	it('getHostExposure parses response', async () => {
		const mockData = {
			last_scan_at: '2026-05-09T14:00:00Z',
			counts: { NETWORK_EXPOSED: 4, ACTIVE: 12, INSTALLED_ONLY: 38, UNKNOWN: 0 },
			advisories: [
				{ advisory_id: 'CVE-1', exposure_tier: 'NETWORK_EXPOSED' as const,
					evidence: ['listening tcp/443 (nginx)'] },
			],
		};
		(apiFetch as any).mockResolvedValue(mockData);
		const e = await getHostExposure('h-1');
		expect(e.counts.NETWORK_EXPOSED).toBe(4);
		expect(e.advisories[0].advisory_id).toBe('CVE-1');
	});

	it('rescanExposure posts', async () => {
		(apiFetch as any).mockResolvedValue({ delivered: true });
		const result = await rescanExposure('h-1');
		expect(result.delivered).toBe(true);
	});

	it('getHostExposure throws on error', async () => {
		const err = new Error('not found');
		(apiFetch as any).mockRejectedValue(err);
		await expect(getHostExposure('h-1')).rejects.toThrow();
	});
});
