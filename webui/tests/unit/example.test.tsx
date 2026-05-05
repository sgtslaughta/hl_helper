import { RiskBadge } from '@/components/security/risk-badge';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

describe('RiskBadge', () => {
	it('renders low risk badge', () => {
		render(<RiskBadge level="low" />);
		expect(screen.getByText('Low')).toBeInTheDocument();
	});

	it('renders medium risk badge', () => {
		render(<RiskBadge level="medium" />);
		expect(screen.getByText('Medium')).toBeInTheDocument();
	});

	it('renders high risk badge', () => {
		render(<RiskBadge level="high" />);
		expect(screen.getByText('High')).toBeInTheDocument();
	});

	it('displays description as title', () => {
		const desc = 'Critical vulnerability';
		render(<RiskBadge level="high" description={desc} />);
		expect(screen.getByTitle(desc)).toBeInTheDocument();
	});
});
