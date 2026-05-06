import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { OverviewDashboard } from '@/components/hosts/mission-control/overview-dashboard';
import type { Host } from '@/lib/api/hosts';

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

describe('OverviewDashboard', () => {
  it('renders all 6 KPI cards', () => {
    render(<OverviewDashboard host={host} onJump={() => {}} />);
    for (const l of ['Status', 'CPU', 'Mem', 'Disk', 'Net', 'Uptime']) {
      expect(screen.getByText(l)).toBeInTheDocument();
    }
  });

  it('renders identity strip with hostname/os/labels', () => {
    render(<OverviewDashboard host={host} onJump={() => {}} />);
    expect(screen.getByText(/linux/)).toBeInTheDocument();
    expect(screen.getByText('prod')).toBeInTheDocument();
    expect(screen.getByText('web')).toBeInTheDocument();
  });

  it('clicking the Tasks jump link calls onJump("tasks")', () => {
    const onJump = vi.fn();
    render(<OverviewDashboard host={host} onJump={onJump} />);
    fireEvent.click(screen.getByRole('button', { name: /jump to Tasks/i }));
    expect(onJump).toHaveBeenCalledWith('tasks');
  });

  it('clicking the Posture jump link calls onJump("posture")', () => {
    const onJump = vi.fn();
    render(<OverviewDashboard host={host} onJump={onJump} />);
    fireEvent.click(screen.getByRole('button', { name: /jump to Posture/i }));
    expect(onJump).toHaveBeenCalledWith('posture');
  });
});
