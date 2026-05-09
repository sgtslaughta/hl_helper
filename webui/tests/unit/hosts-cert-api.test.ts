import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getHostCert, rotateCertNow, mintReenrollToken } from '@/lib/api/hosts';

vi.mock('@/lib/api-client', () => ({
	apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api-client';

describe('hosts cert API', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('getHostCert parses response', async () => {
		(apiFetch as any).mockResolvedValue({
			serial: 'ABCD',
			issued_at: '2026-05-09T12:00:00Z',
			expires_at: '2026-05-16T12:00:00Z',
			rotation_count: 2,
			last_rotated_at: null,
			last_reenroll_at: null,
			status: 'healthy',
		});
		const c = await getHostCert('h-1');
		expect(c.serial).toBe('ABCD');
		expect(c.status).toBe('healthy');
	});

	it('rotateCertNow posts', async () => {
		(apiFetch as any).mockResolvedValue({ delivered: true });
		const r = await rotateCertNow('h-1');
		expect(r.delivered).toBe(true);
	});

	it('mintReenrollToken returns install_command', async () => {
		(apiFetch as any).mockResolvedValue({
			token_id: 't1',
			token: 'hlb_xyz',
			expires_at: '2026-05-09T12:30:00Z',
			install_command: 'sudo hl-agent reenroll --token hlb_xyz',
		});
		const m = await mintReenrollToken('h-1');
		expect(m.token).toBe('hlb_xyz');
	});
});
