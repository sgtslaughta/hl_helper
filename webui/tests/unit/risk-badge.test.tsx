import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { RiskBadge } from '@/components/primitives/risk-badge';

describe('RiskBadge', () => {
  it('renders the variant text', () => {
    render(<RiskBadge variant="caution" />);
    expect(screen.getByText(/caution/i)).toBeInTheDocument();
  });

  it('applies destructive class for destructive variant', () => {
    render(<RiskBadge variant="destructive" data-testid="b" />);
    expect(screen.getByTestId('b').className).toMatch(/orange|destructive/);
  });

  it('applies irreversible class for irreversible variant', () => {
    render(<RiskBadge variant="irreversible" data-testid="b" />);
    expect(screen.getByTestId('b').className).toMatch(/red|irreversible/);
  });
});
