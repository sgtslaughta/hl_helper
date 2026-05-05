'use client';

import { useState } from 'react';

type TargetMode = 'hosts' | 'groups' | 'tags';

interface Target {
	id: string;
	name: string;
}

interface TargetPickerProps {
	hosts: Target[];
	groups?: Target[];
	tags?: Target[];
	onSelect?: (mode: TargetMode, targets: Target[]) => void;
}

export function TargetPicker({ hosts, groups = [], tags = [], onSelect }: TargetPickerProps) {
	const [mode, setMode] = useState<TargetMode>('hosts');
	const [selected, setSelected] = useState<Set<string>>(new Set());

	const currentTargets = {
		hosts,
		groups,
		tags,
	}[mode];

	const handleToggle = (id: string) => {
		const newSelected = new Set(selected);
		if (newSelected.has(id)) {
			newSelected.delete(id);
		} else {
			newSelected.add(id);
		}
		setSelected(newSelected);
		const selectedTargets = currentTargets.filter(t => newSelected.has(t.id));
		onSelect?.(mode, selectedTargets);
	};

	return (
		<div className="rounded border border-hairline bg-surface p-4 space-y-4">
			<div>
				<h3 className="text-sm font-semibold text-text mb-3">Select Targets</h3>
				<div className="flex gap-2 mb-4">
					{(['hosts', 'groups', 'tags'] as const).map(m => (
						<label key={m} className="flex items-center gap-2 cursor-pointer">
							<input
								type="radio"
								name="target-mode"
								value={m}
								checked={mode === m}
								onChange={() => setMode(m)}
								className="rounded"
							/>
							<span className="text-sm text-text capitalize">{m}</span>
						</label>
					))}
				</div>
			</div>

			<div className="max-h-48 overflow-y-auto space-y-2">
				{currentTargets.map(target => (
					<label
						key={target.id}
						className="flex items-center gap-2 cursor-pointer p-2 hover:bg-surface-2 rounded"
					>
						<input
							type="checkbox"
							checked={selected.has(target.id)}
							onChange={() => handleToggle(target.id)}
							className="rounded"
						/>
						<span className="text-sm text-text">{target.name}</span>
					</label>
				))}
			</div>

			<p className="text-xs text-text-dim">{selected.size} target(s) selected</p>
		</div>
	);
}
