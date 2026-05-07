import { HardwarePanel } from '@/components/hosts/mission-control/hardware-panel';
import type { Host, HostSurvey, HostMetrics } from '@/lib/api/hosts';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

const baseSurvey: HostSurvey = {
	os: 'Ubuntu',
	os_version: '22.04',
	kernel: '5.15.0-86-generic',
	arch: 'x86_64',
	virt: 'kvm',
	cpu_model: 'Intel(R) Core(TM) i7-9700K',
	cpu_cores: 8,
	cpu_threads: 16,
	mem_total_bytes: 16 * 1024 ** 3,
	disks: [{ device: '/dev/sda', mount: '/', fstype: 'ext4', size_bytes: 256 * 1024 ** 3 }],
	nics: [{ name: 'eth0', mac: '00:11:22:33:44:55', ipv4: ['192.168.1.10'], ipv6: [], speed_mbps: 1000 }],
	bios_vendor: 'AMI',
	bios_version: '1.0',
	board_vendor: 'Gigabyte',
	board_product: 'Z390 Aorus',
	collected_at: '2026-05-06T10:00:00Z',
};

const baseMetrics: HostMetrics = {
	load_1: 0.5,
	load_5: 0.3,
	load_15: 0.2,
	mem_used_pct: 45,
	disk_used_pct: 60,
	uptime_seconds: 864000,
};

const baseHost: Host = {
	id: 'h1',
	hostname: 'web-01',
	display_name: null,
	status: 'healthy',
	enrolled_at: '2026-05-01T00:00:00Z',
	last_seen_at: null,
	labels: {},
};

describe('HardwarePanel', () => {
	it('shows "Not yet surveyed" when no survey data', () => {
		render(<HardwarePanel host={baseHost} />);
		expect(screen.getByText(/Not yet surveyed/i)).toBeInTheDocument();
	});

	it('shows "No metrics yet" when no metrics data', () => {
		render(<HardwarePanel host={baseHost} />);
		expect(screen.getByText(/No metrics yet/i)).toBeInTheDocument();
	});

	it('renders hardware survey when data present', () => {
		const host: Host = {
			...baseHost,
			survey: baseSurvey,
			survey_at: '2026-05-06T10:00:00Z',
		};
		render(<HardwarePanel host={host} />);
		expect(screen.getByText(/Ubuntu/)).toBeInTheDocument();
		expect(screen.getByText(/Intel.*i7-9700K/)).toBeInTheDocument();
		expect(screen.getByText(/8 cores/)).toBeInTheDocument();
		expect(screen.getByText(/16 threads/)).toBeInTheDocument();
		expect(screen.getByText(/16.0 GB/)).toBeInTheDocument();
	});

	it('renders metrics when data present', () => {
		const host: Host = {
			...baseHost,
			metrics: baseMetrics,
			metrics_at: '2026-05-06T10:05:00Z',
		};
		render(<HardwarePanel host={host} />);
		expect(screen.getByText(/0.50/)).toBeInTheDocument();
		expect(screen.getByText(/45%/)).toBeInTheDocument();
		expect(screen.getByText(/60%/)).toBeInTheDocument();
	});

	it('formats uptime in days', () => {
		const host: Host = {
			...baseHost,
			metrics: baseMetrics,
			metrics_at: '2026-05-06T10:05:00Z',
		};
		render(<HardwarePanel host={host} />);
		expect(screen.getByText(/10d/)).toBeInTheDocument();
	});
});
