import { SourceBadge } from '@/components/settings/source-badge';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

describe('SourceBadge', () => {
	it('should render Runtime label for runtime source', () => {
		render(<SourceBadge source="runtime" />);
		expect(screen.getByText('Runtime')).toBeInTheDocument();
	});

	it('should render Environment label for env source', () => {
		render(<SourceBadge source="env" />);
		expect(screen.getByText('Environment')).toBeInTheDocument();
	});

	it('should render File label for file source', () => {
		render(<SourceBadge source="file" />);
		expect(screen.getByText('File')).toBeInTheDocument();
	});

	it('should render Default label for default source', () => {
		render(<SourceBadge source="default" />);
		expect(screen.getByText('Default')).toBeInTheDocument();
	});
});
