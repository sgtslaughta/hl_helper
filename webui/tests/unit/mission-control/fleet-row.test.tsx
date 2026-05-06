import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FleetRow } from '@/components/hosts/mission-control/fleet-row';
import type { Host } from '@/lib/api/hosts';

const host: Host = {
  id: 'h1',
  hostname: 'web-01',
  display_name: 'web-01.prod',
  status: 'healthy',
  enrolled_at: '2026-05-01T00:00:00Z',
  last_seen_at: '2026-05-06T18:00:00Z',
  labels: {},
  os: 'linux',
  os_version: '24.04',
  cpu_pct: 22,
  mem_pct: 41,
};

describe('FleetRow', () => {
  it('lean: shows only status dot + name', () => {
    render(<FleetRow host={host} density="lean" selected={false} onSelect={() => {}} />);
    expect(screen.getByText('web-01.prod')).toBeInTheDocument();
    expect(screen.queryByText(/cpu/i)).not.toBeInTheDocument();
  });

  it('balanced: shows OS tag, cpu/mem, last-seen', () => {
    render(<FleetRow host={host} density="balanced" selected={false} onSelect={() => {}} />);
    expect(screen.getByText('linux')).toBeInTheDocument();
    expect(screen.getByText(/22%/)).toBeInTheDocument();
    expect(screen.getByText(/41%/)).toBeInTheDocument();
  });

  it('rich: shows sparkline (svg)', () => {
    const { container } = render(
      <FleetRow host={host} density="rich" selected={false} onSelect={() => {}} cpuHistory={[10, 20, 30]} />,
    );
    expect(container.querySelector('svg')).toBeInTheDocument();
  });

  it('selected row gets aria-selected', () => {
    render(<FleetRow host={host} density="balanced" selected onSelect={() => {}} />);
    expect(screen.getByRole('option')).toHaveAttribute('aria-selected', 'true');
  });

  it('fires onSelect with host id', () => {
    const onSelect = vi.fn();
    render(<FleetRow host={host} density="balanced" selected={false} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole('option'));
    expect(onSelect).toHaveBeenCalledWith('h1');
  });

  it('shows "offline" instead of metrics when status is offline', () => {
    render(
      <FleetRow
        host={{ ...host, status: 'offline' }}
        density="balanced"
        selected={false}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText(/offline/i)).toBeInTheDocument();
  });
});
