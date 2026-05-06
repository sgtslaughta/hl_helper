import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { QuickActions } from '@/components/hosts/mission-control/quick-actions';
import type { Host } from '@/lib/api/hosts';

const host: Host = {
  id: 'h1',
  hostname: 'web-01',
  display_name: null,
  status: 'healthy',
  enrolled_at: '2026-05-01T00:00:00Z',
  last_seen_at: null,
  labels: {},
};

vi.mock('@/lib/rbac', () => ({
  useCanPerform: (action: string) => ({
    allowed: action !== 'revoke-host',
    reason: action === 'revoke-host' ? 'denied for tests' : '',
    principal: 'u',
  }),
}));

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('QuickActions', () => {
  it('renders the 4 supported actions', () => {
    render(wrap(<QuickActions host={host} />));
    for (const label of ['Reboot', 'Run shell', 'Patch', 'Revoke']) {
      expect(screen.getByRole('button', { name: new RegExp(label, 'i') })).toBeInTheDocument();
    }
  });

  it('disables an RBAC-denied action and surfaces reason in tooltip', () => {
    render(wrap(<QuickActions host={host} />));
    const revoke = screen.getByRole('button', { name: /Revoke/i });
    expect(revoke).toBeDisabled();
    expect(revoke).toHaveAttribute('title', expect.stringMatching(/denied/));
  });

  it('clicking an allowed action opens confirm dialog', () => {
    render(wrap(<QuickActions host={host} />));
    fireEvent.click(screen.getByRole('button', { name: /Reboot/i }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});
