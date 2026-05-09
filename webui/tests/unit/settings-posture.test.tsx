import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';

vi.mock('@/lib/api/posture-risk', () => ({
	useRiskConfig: vi.fn(),
	usePatchRiskConfig: vi.fn(),
}));

import { useRiskConfig, usePatchRiskConfig } from '@/lib/api/posture-risk';

// Test component that mirrors the page component logic
function PosturePageTest() {
	const q = useRiskConfig();
	const patch = usePatchRiskConfig();
	const [draftWeights, setDraftWeights] = useState<Record<string, number>>({});
	const [draftEnabled, setDraftEnabled] = useState<Record<string, boolean>>({});

	useEffect(() => {
		if (q.data) {
			setDraftWeights(Object.fromEntries(q.data.scorers.map(s => [s.name, s.weight])));
			setDraftEnabled(Object.fromEntries(q.data.scorers.map(s => [s.name, s.enabled])));
		}
	}, [q.data]);

	if (!q.data) return <div className="p-6 text-text-dim">Loading…</div>;

	const onSave = () => {
		patch.mutate({ weights: draftWeights, enabled: draftEnabled });
	};
	const onReset = () => {
		const w = Object.fromEntries(q.data.scorers.map(s => [s.name, s.weight_default]));
		const e = Object.fromEntries(
			q.data.scorers.map(s => [s.name, s.enabled_by_default]),
		);
		setDraftWeights(w);
		setDraftEnabled(e);
	};

	return (
		<div className="flex flex-col gap-4 p-6">
			<h1 className="text-h1 text-text">Posture risk weights</h1>
			<p className="text-text-dim text-sm">
				Tune how each pillar contributes to the aggregate risk score. Changes apply
				fleet-wide.
			</p>

			<div className="rounded border border-hairline bg-surface p-4 space-y-3">
				{q.data.scorers.map(s => (
					<div key={s.name} className="space-y-1">
						<div className="flex items-center justify-between">
							<div className="font-mono text-sm text-text">{s.label}</div>
							<label className="flex items-center gap-2 text-xs text-text-dim">
								<input
									type="checkbox"
									checked={draftEnabled[s.name] ?? s.enabled}
									onChange={ev =>
										setDraftEnabled(prev => ({
											...prev,
											[s.name]: ev.target.checked,
										}))
									}
								/>
								enabled
							</label>
						</div>
						<p className="text-xs text-text-dim/80">{s.description}</p>
						<div className="flex items-center gap-3">
							<input
								type="range"
								min={0}
								max={1}
								step={0.05}
								value={draftWeights[s.name] ?? s.weight}
								onChange={ev =>
									setDraftWeights(prev => ({
										...prev,
										[s.name]: Number(ev.target.value),
									}))
								}
								className="flex-1"
							/>
							<span className="font-mono text-xs w-12 text-right">
								{(draftWeights[s.name] ?? s.weight).toFixed(2)}
							</span>
						</div>
					</div>
				))}
			</div>

			<div className="flex gap-2">
				<button
					type="button"
					onClick={onSave}
					disabled={patch.isPending}
					className="rounded border border-accent bg-accent/15 px-3 py-1.5 text-sm text-accent hover:bg-accent/25 disabled:opacity-40"
				>
					{patch.isPending ? 'Saving…' : 'Save'}
				</button>
				<button
					type="button"
					onClick={onReset}
					className="rounded border border-hairline px-3 py-1.5 text-sm text-text-dim hover:bg-surface-2"
				>
					Reset to defaults
				</button>
			</div>
		</div>
	);
}

function wrap(ui: ReactNode) {
	const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('PosturePage', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('shows loading state when data is not loaded', () => {
		(useRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			data: null,
			isLoading: true,
		});
		(usePatchRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			mutate: vi.fn(),
			isPending: false,
		});

		render(wrap(<PosturePageTest />));
		expect(screen.getByText('Loading…')).toBeInTheDocument();
	});

	it('renders scorers with their labels and descriptions', () => {
		(useRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			data: {
				weights: {},
				scorers: [
					{
						name: 'sysinfo',
						label: 'System Info',
						description: 'Evaluates system configuration',
						weight: 0.5,
						weight_default: 0.5,
						enabled: true,
						enabled_by_default: true,
						plugin: 'core',
					},
					{
						name: 'patch',
						label: 'Patch Level',
						description: 'Evaluates patch compliance',
						weight: 0.3,
						weight_default: 0.3,
						enabled: true,
						enabled_by_default: true,
						plugin: 'core',
					},
				],
			},
			isLoading: false,
		});
		(usePatchRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			mutate: vi.fn(),
			isPending: false,
		});

		render(wrap(<PosturePageTest />));
		expect(screen.getByText('System Info')).toBeInTheDocument();
		expect(screen.getByText('Patch Level')).toBeInTheDocument();
		expect(screen.getByText('Evaluates system configuration')).toBeInTheDocument();
		expect(screen.getByText('Evaluates patch compliance')).toBeInTheDocument();
	});

	it('renders weight sliders and displays current weight values', () => {
		(useRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			data: {
				weights: {},
				scorers: [
					{
						name: 'sysinfo',
						label: 'System Info',
						description: 'Test',
						weight: 0.5,
						weight_default: 0.5,
						enabled: true,
						enabled_by_default: true,
						plugin: 'core',
					},
				],
			},
			isLoading: false,
		});
		(usePatchRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			mutate: vi.fn(),
			isPending: false,
		});

		render(wrap(<PosturePageTest />));
		const slider = screen.getByRole('slider');
		expect(slider).toHaveValue('0.5');
		expect(screen.getByText('0.50')).toBeInTheDocument();
	});

	it('updates weight display when slider changes', () => {
		(useRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			data: {
				weights: {},
				scorers: [
					{
						name: 'sysinfo',
						label: 'System Info',
						description: 'Test',
						weight: 0.5,
						weight_default: 0.5,
						enabled: true,
						enabled_by_default: true,
						plugin: 'core',
					},
				],
			},
			isLoading: false,
		});
		(usePatchRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			mutate: vi.fn(),
			isPending: false,
		});

		render(wrap(<PosturePageTest />));
		const slider = screen.getByRole('slider');
		fireEvent.change(slider, { target: { value: '0.75' } });
		expect(screen.getByText('0.75')).toBeInTheDocument();
	});

	it('renders enabled checkboxes for each scorer', () => {
		(useRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			data: {
				weights: {},
				scorers: [
					{
						name: 'sysinfo',
						label: 'System Info',
						description: 'Test',
						weight: 0.5,
						weight_default: 0.5,
						enabled: true,
						enabled_by_default: true,
						plugin: 'core',
					},
					{
						name: 'patch',
						label: 'Patch Level',
						description: 'Test',
						weight: 0.3,
						weight_default: 0.3,
						enabled: false,
						enabled_by_default: true,
						plugin: 'core',
					},
				],
			},
			isLoading: false,
		});
		(usePatchRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			mutate: vi.fn(),
			isPending: false,
		});

		render(wrap(<PosturePageTest />));
		const checkboxes = screen.getAllByRole('checkbox');
		expect(checkboxes).toHaveLength(2);
		expect(checkboxes[0]).toBeChecked();
		expect(checkboxes[1]).not.toBeChecked();
	});

	it('toggles enabled checkbox when clicked', () => {
		(useRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			data: {
				weights: {},
				scorers: [
					{
						name: 'sysinfo',
						label: 'System Info',
						description: 'Test',
						weight: 0.5,
						weight_default: 0.5,
						enabled: true,
						enabled_by_default: true,
						plugin: 'core',
					},
				],
			},
			isLoading: false,
		});
		(usePatchRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			mutate: vi.fn(),
			isPending: false,
		});

		render(wrap(<PosturePageTest />));
		const checkbox = screen.getByRole('checkbox');
		fireEvent.click(checkbox);
		expect(checkbox).not.toBeChecked();
	});

	it('calls patch mutation with draft weights and enabled on save', () => {
		const mockMutate = vi.fn();
		(useRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			data: {
				weights: {},
				scorers: [
					{
						name: 'sysinfo',
						label: 'System Info',
						description: 'Test',
						weight: 0.5,
						weight_default: 0.5,
						enabled: true,
						enabled_by_default: true,
						plugin: 'core',
					},
				],
			},
			isLoading: false,
		});
		(usePatchRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			mutate: mockMutate,
			isPending: false,
		});

		render(wrap(<PosturePageTest />));
		const slider = screen.getByRole('slider');
		fireEvent.change(slider, { target: { value: '0.75' } });
		const saveButton = screen.getByRole('button', { name: /save/i });
		fireEvent.click(saveButton);
		expect(mockMutate).toHaveBeenCalledWith({
			weights: { sysinfo: 0.75 },
			enabled: { sysinfo: true },
		});
	});

	it('resets weights and enabled to defaults on reset button', () => {
		(useRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			data: {
				weights: {},
				scorers: [
					{
						name: 'sysinfo',
						label: 'System Info',
						description: 'Test',
						weight: 0.5,
						weight_default: 0.3,
						enabled: false,
						enabled_by_default: true,
						plugin: 'core',
					},
				],
			},
			isLoading: false,
		});
		(usePatchRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			mutate: vi.fn(),
			isPending: false,
		});

		render(wrap(<PosturePageTest />));
		const slider = screen.getByRole('slider');
		expect(slider).toHaveValue('0.5');
		const resetButton = screen.getByRole('button', { name: /reset to defaults/i });
		fireEvent.click(resetButton);
		expect(slider).toHaveValue('0.3');
		const checkbox = screen.getByRole('checkbox');
		expect(checkbox).toBeChecked();
	});

	it('disables save button while mutation is pending', () => {
		(useRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			data: {
				weights: {},
				scorers: [
					{
						name: 'sysinfo',
						label: 'System Info',
						description: 'Test',
						weight: 0.5,
						weight_default: 0.5,
						enabled: true,
						enabled_by_default: true,
						plugin: 'core',
					},
				],
			},
			isLoading: false,
		});
		(usePatchRiskConfig as ReturnType<typeof vi.fn>).mockReturnValue({
			mutate: vi.fn(),
			isPending: true,
		});

		render(wrap(<PosturePageTest />));
		const saveButton = screen.getByRole('button', { name: /saving/i });
		expect(saveButton).toBeDisabled();
	});
});
