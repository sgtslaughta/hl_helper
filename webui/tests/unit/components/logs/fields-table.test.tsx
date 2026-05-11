import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FieldsTable } from '@/components/logs/fields-table';
import { describe, it, expect, beforeEach, vi } from 'vitest';

let mockWriteText: any;

beforeEach(() => {
	mockWriteText = vi.fn().mockResolvedValue(undefined);
	vi.stubGlobal('navigator', {
		clipboard: {
			writeText: mockWriteText,
		},
	});
});

describe('FieldsTable', () => {

	it('renders flat object', () => {
		const obj = {
			ts: '2026-05-10T22:15:03Z',
			action: 'task.exec.completed',
			level: 'info',
		};

		render(<FieldsTable obj={obj} />);

		expect(screen.getByTitle('ts')).toBeInTheDocument();
		expect(screen.getByTitle('action')).toBeInTheDocument();
		expect(screen.getByTitle('level')).toBeInTheDocument();
		expect(screen.getByText('2026-05-10T22:15:03Z')).toBeInTheDocument();
	});

	it('renders nested object with dot notation', async () => {
		const obj = {
			details: {
				host: {
					os: 'linux',
					arch: 'x86_64',
				},
				rc: 0,
			},
		};

		render(<FieldsTable obj={obj} />);
		const user = userEvent.setup();

		// Expand details group (group header still uses raw label)
		const detailsButton = screen.getByRole('button', { name: /details/i });
		await user.click(detailsButton);

		expect(screen.getByTitle('details.host.os')).toBeInTheDocument();
		expect(screen.getByTitle('details.host.arch')).toBeInTheDocument();
		expect(screen.getByTitle('details.rc')).toBeInTheDocument();
	});

	it('renders array of primitives as comma-separated string', () => {
		const obj = {
			tags: ['tag1', 'tag2', 'tag3'],
		};

		render(<FieldsTable obj={obj} />);

		expect(screen.getByTitle('tags')).toBeInTheDocument();
		expect(screen.getByText('tag1, tag2, tag3')).toBeInTheDocument();
	});

	it('renders array of objects with index notation', async () => {
		const obj = {
			items: [{ id: '1', name: 'first' }, { id: '2', name: 'second' }],
		};

		render(<FieldsTable obj={obj} />);
		const user = userEvent.setup();

		// Items group is collapsible, so first expand it
		const itemsButton = screen.getByRole('button', { name: /items/i });
		await user.click(itemsButton);

		expect(screen.getByTitle('items[0].id')).toBeInTheDocument();
		expect(screen.getByTitle('items[0].name')).toBeInTheDocument();
		expect(screen.getByText('1')).toBeInTheDocument();
		expect(screen.getByText('first')).toBeInTheDocument();
	});

	it('handles null values', () => {
		const obj = {
			field1: null,
			field2: 'value',
		};

		render(<FieldsTable obj={obj} />);

		expect(screen.getByText('null')).toBeInTheDocument();
		expect(screen.getByText('value')).toBeInTheDocument();
	});

	it('handles empty arrays', () => {
		const obj = {
			empty: [],
		};

		render(<FieldsTable obj={obj} />);

		expect(screen.getByText('[]')).toBeInTheDocument();
	});

	it('renders error object when provided', () => {
		const obj = { test: 'value' };
		const errorObj = {
			code: 'ERR_TIMEOUT',
			message: 'Request timeout after 30s',
		};

		render(<FieldsTable obj={obj} errorObj={errorObj} />);

		expect(screen.getByText('Error')).toBeInTheDocument();
		expect(screen.getByText('Code: ERR_TIMEOUT')).toBeInTheDocument();
		expect(screen.getByText('Request timeout after 30s')).toBeInTheDocument();
	});

	it('renders error with stack trace', () => {
		const obj = { test: 'value' };
		const errorObj = {
			code: 'ERR_EXEC',
			message: 'Execution failed',
			stack_trace: 'at exec (runner.js:42)\nat run (main.js:10)',
		};

		render(<FieldsTable obj={obj} errorObj={errorObj} />);

		const summary = screen.getByText('Stack trace');
		expect(summary).toBeInTheDocument();
	});

	it('renders fields inside a horizontally-scrollable table', () => {
		const obj = {
			ts: '2026-05-10T22:15:03Z',
			action: 'task.exec.completed',
		};

		const { container } = render(<FieldsTable obj={obj} />);

		const scroller = container.querySelector('.overflow-x-auto');
		expect(scroller).toBeInTheDocument();
		const table = container.querySelector('table');
		expect(table).toBeInTheDocument();
		expect(table?.tagName).toBe('TABLE');
	});

	it('groups fields by top-level prefix', () => {
		const obj = {
			ts: '2026-05-10T22:15:03Z',
			level: 'info',
			labels: {
				command_id: 'cmd-abc',
				plugin: 'docker',
			},
			details: {
				rc: 0,
				host: {
					os: 'linux',
				},
			},
		};

		render(<FieldsTable obj={obj} />);

		// Check for group headers - look for buttons that contain the text
		const labelButtons = screen.getAllByRole('button');
		const hasLabels = labelButtons.some((btn) => btn.textContent?.includes('labels'));
		const hasDetails = labelButtons.some((btn) => btn.textContent?.includes('details'));
		expect(hasLabels).toBe(true);
		expect(hasDetails).toBe(true);
	});

	it('handles mixed types correctly', () => {
		const obj = {
			count: 42,
			enabled: true,
			disabled: false,
			name: 'test',
			missing: null,
		};

		const { container } = render(<FieldsTable obj={obj} />);

		// These are all at root level, so they should be visible without expanding
		expect(screen.getByTitle('count')).toBeInTheDocument();
		expect(screen.getByText('42')).toBeInTheDocument();
		expect(screen.getByTitle('enabled')).toBeInTheDocument();
		expect(screen.getByTitle('disabled')).toBeInTheDocument();
		expect(screen.getByTitle('name')).toBeInTheDocument();
		expect(screen.getByText('test')).toBeInTheDocument();
		expect(screen.getByTitle('missing')).toBeInTheDocument();
	});

	it('handles deeply nested objects', () => {
		const obj = {
			a: {
				b: {
					c: {
						d: 'value',
					},
				},
			},
		};

		render(<FieldsTable obj={obj} />);

		// Single item groups don't show a collapse button, so content is visible
		expect(screen.getByTitle('a.b.c.d')).toBeInTheDocument();
		expect(screen.getByText('value')).toBeInTheDocument();
	});

	it('handles undefined and null at top level', () => {
		const { container: container1 } = render(<FieldsTable obj={null} />);
		// Should render empty space structure
		expect(container1).toBeInTheDocument();

		const { container: container2 } = render(<FieldsTable obj={undefined} />);
		expect(container2).toBeInTheDocument();
	});

	it('handles non-object primitive at root', () => {
		render(<FieldsTable obj="just a string" />);

		expect(screen.getByText('just a string')).toBeInTheDocument();
	});
});
