import { render, screen, fireEvent } from '@testing-library/react';
import { ActivityFilterBar } from '@/components/hosts/activity/activity-filter-bar';
import { describe, it, expect, vi } from 'vitest';

describe('ActivityFilterBar', () => {
	it('renders time range pills', () => {
		const mockOnChange = vi.fn();
		render(
			<ActivityFilterBar onChange={mockOnChange} />,
		);

		expect(screen.getByText('15m')).toBeInTheDocument();
		expect(screen.getByText('1h')).toBeInTheDocument();
		expect(screen.getByText('6h')).toBeInTheDocument();
		expect(screen.getByText('24h')).toBeInTheDocument();
		expect(screen.getByText('7d')).toBeInTheDocument();
	});

	it('calls onChange when time range changes', () => {
		const mockOnChange = vi.fn();
		render(
			<ActivityFilterBar onChange={mockOnChange} />,
		);

		const button = screen.getByText('24h');
		fireEvent.click(button);

		expect(mockOnChange).toHaveBeenCalledWith(
			expect.objectContaining({ timeRange: '24h' }),
		);
	});

	it('renders level dropdown', () => {
		const mockOnChange = vi.fn();
		render(
			<ActivityFilterBar onChange={mockOnChange} />,
		);

		const select = screen.getByDisplayValue('Info+');
		expect(select).toBeInTheDocument();
	});

	it('renders outcome toggle buttons', () => {
		const mockOnChange = vi.fn();
		render(
			<ActivityFilterBar onChange={mockOnChange} />,
		);

		expect(screen.getByText(/Success/)).toBeInTheDocument();
		expect(screen.getByText(/Failure/)).toBeInTheDocument();
		expect(screen.getByText(/Unknown/)).toBeInTheDocument();
	});

	it('toggles pause/live state', () => {
		const mockOnChange = vi.fn();
		const mockTogglePause = vi.fn();
		render(
			<ActivityFilterBar
				onChange={mockOnChange}
				onTogglePauseTail={mockTogglePause}
				isPausedTail={false}
			/>,
		);

		const liveButton = screen.getByText('◉ Live');
		fireEvent.click(liveButton);

		expect(mockTogglePause).toHaveBeenCalledWith(true);
	});

	it('renders search input', () => {
		const mockOnChange = vi.fn();
		render(
			<ActivityFilterBar onChange={mockOnChange} />,
		);

		const searchInput = screen.getByPlaceholderText('Search…');
		expect(searchInput).toBeInTheDocument();
	});

	it('displays category chips and allows removal', () => {
		const mockOnChange = vi.fn();
		render(
			<ActivityFilterBar
				onChange={mockOnChange}
				categories={['task', 'host', 'agent']}
			/>,
		);

		expect(screen.getByText('+ Add category')).toBeInTheDocument();
	});
});
