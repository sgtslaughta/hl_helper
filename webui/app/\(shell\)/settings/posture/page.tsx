'use client';

import { usePatchRiskConfig, useRiskConfig } from '@/lib/api/posture-risk';
import { useEffect, useState } from 'react';

export default function PosturePage() {
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
		const e = Object.fromEntries(q.data.scorers.map(s => [s.name, s.enabled_by_default]));
		setDraftWeights(w);
		setDraftEnabled(e);
	};

	return (
		<div className="flex flex-col gap-4 p-6">
			<h1 className="text-h1 text-text">Posture risk weights</h1>
			<p className="text-text-dim text-sm">
				Tune how each pillar contributes to the aggregate risk score. Changes apply fleet-wide.
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
