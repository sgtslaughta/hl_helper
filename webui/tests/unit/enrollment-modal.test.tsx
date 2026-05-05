import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { EnrollmentModal } from '@/components/hosts/enrollment-modal';

vi.mock('@/lib/api/enrollment', () => ({
  mintEnrollmentToken: vi.fn(),
  listPendingTokens: vi.fn().mockResolvedValue([]),
  revokePendingToken: vi.fn(),
}));

import { mintEnrollmentToken } from '@/lib/api/enrollment';

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('EnrollmentModal step 1', () => {
  beforeEach(() => vi.clearAllMocks());

  it('disables submit when label empty', () => {
    render(wrap(<EnrollmentModal onClose={vi.fn()} />));
    expect(screen.getByRole('button', { name: /mint token/i })).toBeDisabled();
  });

  it('submits with label and ttl', async () => {
    (mintEnrollmentToken as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({
      token_id: 'et_1',
      plaintext_token: 'hlh_enr_abc',
      expires_at: new Date(Date.now() + 900_000).toISOString(),
      install_command: 'curl ... --token=hlh_enr_abc',
    });
    render(wrap(<EnrollmentModal onClose={vi.fn()} />));
    fireEvent.change(screen.getByLabelText(/label/i), { target: { value: 'lab-01' } });
    fireEvent.click(screen.getByRole('button', { name: /mint token/i }));
    await waitFor(() =>
      expect(mintEnrollmentToken).toHaveBeenCalledWith({ label: 'lab-01', ttl_seconds: 900 })
    );
  });
});
