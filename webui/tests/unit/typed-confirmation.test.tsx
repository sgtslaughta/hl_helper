import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { TypedConfirmation } from '@/components/primitives/typed-confirmation';

describe('TypedConfirmation', () => {
  it('emits match=true only on exact equality', () => {
    const onMatch = vi.fn();
    render(<TypedConfirmation expected="lab-router" onMatch={onMatch} />);
    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'lab-rout' } });
    expect(onMatch).toHaveBeenLastCalledWith(false);
    fireEvent.change(input, { target: { value: 'lab-router' } });
    expect(onMatch).toHaveBeenLastCalledWith(true);
  });
});
