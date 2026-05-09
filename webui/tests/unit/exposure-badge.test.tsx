import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ExposureBadge } from '@/components/hosts/exposure-badge';

describe('ExposureBadge', () => {
	it.each([
		['NETWORK_EXPOSED', /network-exposed/i],
		['ACTIVE', /active/i],
		['INSTALLED_ONLY', /dormant/i],
		['UNKNOWN', /unknown/i],
	])('renders %s tier', (tier, regex) => {
		render(<ExposureBadge tier={tier as any} />);
		expect(screen.getByText(regex)).toBeInTheDocument();
	});
});
