import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { Countdown } from '@/components/primitives/countdown';

describe('Countdown', () => {
  it('renders mm:ss format under one hour', () => {
    const target = new Date(Date.now() + 65_000).toISOString();
    render(<Countdown to={target} />);
    expect(screen.getByText(/01:0\d/)).toBeInTheDocument();
  });

  it('calls onExpire when reaches zero', () => {
    vi.useFakeTimers();
    const onExpire = vi.fn();
    const target = new Date(Date.now() + 1_000).toISOString();
    render(<Countdown to={target} onExpire={onExpire} />);
    act(() => { vi.advanceTimersByTime(2_000); });
    expect(onExpire).toHaveBeenCalled();
    vi.useRealTimers();
  });
});
