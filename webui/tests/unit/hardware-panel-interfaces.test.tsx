import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HardwarePanel } from '@/components/hosts/mission-control/hardware-panel';
import type { Host } from '@/lib/api/hosts';

describe('HardwarePanel network interfaces', () => {
	it('renders interface rows', () => {
		const host: Host = {
			id: 'h1',
			hostname: 'web-01',
			display_name: null,
			status: 'healthy',
			enrolled_at: '2026-05-01T00:00:00Z',
			last_seen_at: null,
			labels: {},
			metrics: {
				load_1: 0.5,
				load_5: 0.3,
				load_15: 0.2,
				mem_used_pct: 45,
				disk_used_pct: 60,
				uptime_seconds: 864000,
				interfaces: [
					{ name: 'eth0', rx_bps: 12345, tx_bps: 6789, rx_errors: 0, tx_errors: 0, up: true, ipv4: ['192.168.1.196'] },
					{ name: 'lo', rx_bps: 200, tx_bps: 200, rx_errors: 0, tx_errors: 0, up: true, ipv4: ['127.0.0.1'] },
				],
			},
			metrics_at: '2026-05-06T10:05:00Z',
		};
		render(<HardwarePanel host={host} />);
		expect(screen.getByText('eth0')).toBeInTheDocument();
		expect(screen.getByText(/192\.168\.1\.196/)).toBeInTheDocument();
	});
});
