import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ActionConfirmDialog } from '@/components/hosts/action-confirm-dialog';

const HOST = { id: 'h1', hostname: 'lab-router-01' };

describe('ActionConfirmDialog', () => {
  it('renders summary and risks for action', () => {
    render(
      <ActionConfirmDialog
        action="reboot"
        host={HOST}
        principal="u1"
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByText(/Reboot host/i)).toBeInTheDocument();
    expect(screen.getByText(/Restarts the host/i)).toBeInTheDocument();
    expect(screen.getByText(/Active sessions/i)).toBeInTheDocument();
  });

  it('disables confirm until hostname typed for irreversible', () => {
    render(
      <ActionConfirmDialog
        action="revoke-host"
        host={HOST}
        principal="u1"
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    );
    const confirm = screen.getByRole('button', { name: /confirm/i });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'lab-router-01' } });
    expect(confirm).toBeEnabled();
  });

  it('calls onConfirm when clicked for non-irreversible', () => {
    const onConfirm = vi.fn();
    render(
      <ActionConfirmDialog
        action="reboot"
        host={HOST}
        principal="u1"
        onConfirm={onConfirm}
        onClose={vi.fn()}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
    expect(onConfirm).toHaveBeenCalled();
  });

  it('renders custom form between risks and disclosures', () => {
    render(
      <ActionConfirmDialog
        action="shell-exec"
        host={HOST}
        principal="u1"
        onConfirm={vi.fn()}
        onClose={vi.fn()}
        formChildren={<input data-testid="cmd" placeholder="cmd" />}
      />
    );
    expect(screen.getByTestId('cmd')).toBeInTheDocument();
  });
});
