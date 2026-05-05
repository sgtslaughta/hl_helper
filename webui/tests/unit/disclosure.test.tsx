import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { Disclosure } from '@/components/primitives/disclosure';

describe('Disclosure', () => {
  beforeEach(() => localStorage.clear());

  it('starts collapsed', () => {
    render(<Disclosure label="Details"><span>secret</span></Disclosure>);
    expect(screen.queryByText('secret')).not.toBeInTheDocument();
  });

  it('expands on click', () => {
    render(<Disclosure label="Details"><span>secret</span></Disclosure>);
    fireEvent.click(screen.getByRole('button', { name: /details/i }));
    expect(screen.getByText('secret')).toBeInTheDocument();
  });

  it('persists expanded state when storageKey provided', () => {
    const { unmount } = render(
      <Disclosure label="X" storageKey="k1"><span>v</span></Disclosure>
    );
    fireEvent.click(screen.getByRole('button', { name: /x/i }));
    unmount();
    render(<Disclosure label="X" storageKey="k1"><span>v</span></Disclosure>);
    expect(screen.getByText('v')).toBeInTheDocument();
  });

  it('respects global override flag', () => {
    localStorage.setItem('hlh.alwaysShowDetails', 'true');
    render(<Disclosure label="X" storageKey="k2"><span>v</span></Disclosure>);
    expect(screen.getByText('v')).toBeInTheDocument();
  });
});
