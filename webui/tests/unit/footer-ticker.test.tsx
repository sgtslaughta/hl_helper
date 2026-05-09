import { render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';
import { FooterTicker } from '@/components/shell/ticker/footer-ticker';

class StubEventSource {
	url: string;
	withCredentials = false;
	onopen: (() => void) | null = null;
	onmessage: ((e: { data: string }) => void) | null = null;
	onerror: (() => void) | null = null;
	constructor(url: string) {
		this.url = url;
	}
	close() {}
}

beforeAll(() => {
	if (typeof globalThis.EventSource === 'undefined') {
		// jsdom lacks EventSource; stub for component mount.
		(globalThis as unknown as { EventSource: typeof StubEventSource }).EventSource =
			StubEventSource;
	}
});

describe('FooterTicker', () => {
	it('renders SYS heading and connecting placeholder before any events', () => {
		render(<FooterTicker />);
		expect(screen.getByLabelText('System ticker')).toBeInTheDocument();
		expect(screen.getByText('SYS')).toBeInTheDocument();
		expect(screen.getByText(/Connecting/i)).toBeInTheDocument();
	});
});
