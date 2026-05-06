import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TopBar } from '@/components/hosts/mission-control/top-bar';

vi.mock('@/lib/rbac', () => ({
  useCanPerform: () => ({ allowed: true, reason: '', principal: 'u' }),
}));

describe('TopBar', () => {
  it('renders health pill counts', () => {
    render(
      <TopBar
        counts={{ critical: 2, pending: 1, online: 14, offline: 1 }}
        onEnroll={() => {}}
        onPalette={() => {}}
      />,
    );
    expect(screen.getByText(/2 critical/i)).toBeInTheDocument();
    expect(screen.getByText(/1 pending/i)).toBeInTheDocument();
    expect(screen.getByText(/14 online/i)).toBeInTheDocument();
  });

  it('clicking palette button triggers onPalette', () => {
    const onPalette = vi.fn();
    render(
      <TopBar
        counts={{ critical: 0, pending: 0, online: 0, offline: 0 }}
        onEnroll={() => {}}
        onPalette={onPalette}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Open palette/i }));
    expect(onPalette).toHaveBeenCalled();
  });

  it('clicking a health pill calls onPillClick', () => {
    const onPillClick = vi.fn();
    render(
      <TopBar
        counts={{ critical: 2, pending: 0, online: 0, offline: 0 }}
        onEnroll={() => {}}
        onPalette={() => {}}
        onPillClick={onPillClick}
      />,
    );
    fireEvent.click(screen.getByText(/2 critical/i));
    expect(onPillClick).toHaveBeenCalledWith('critical');
  });

  it('Enroll button calls onEnroll when clicked (RBAC allowed)', () => {
    const onEnroll = vi.fn();
    render(
      <TopBar
        counts={{ critical: 0, pending: 0, online: 0, offline: 0 }}
        onEnroll={onEnroll}
        onPalette={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Enroll host/i }));
    expect(onEnroll).toHaveBeenCalled();
  });
});
