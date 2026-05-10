import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FilterRail } from '@/components/logs/filter-rail';
import { describe, it, expect, vi } from 'vitest';

describe('FilterRail', () => {
	it('renders all filter sections', () => {
		const onChange = vi.fn();
		render(<FilterRail onChange={onChange} />);
		expect(screen.getByText('Time Range')).toBeInTheDocument();
		expect(screen.getByText('Hosts')).toBeInTheDocument();
		expect(screen.getByText('Level')).toBeInTheDocument();
		expect(screen.getByText('Categories')).toBeInTheDocument();
		expect(screen.getByText('Search')).toBeInTheDocument();
	});

	it('calls onChange when level is selected', async () => {
		const onChange = vi.fn();
		render(<FilterRail onChange={onChange} />);
		const user = userEvent.setup();

		const levelButton = screen.getByText('Level');
		await user.click(levelButton);

		const errorRadio = screen.getByDisplayValue('error');
		await user.click(errorRadio);

		expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ level: 'error' }));
	});

	it('expands and collapses sections on click', async () => {
		const onChange = vi.fn();
		const { container } = render(<FilterRail onChange={onChange} />);
		const user = userEvent.setup();

		const hostsButton = screen.getByText('Hosts');
		await user.click(hostsButton);

		const input = container.querySelector('input[placeholder="Comma-separated hosts"]');
		expect(input).toBeVisible();
	});
});
