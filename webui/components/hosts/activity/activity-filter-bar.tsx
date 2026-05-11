'use client';

import type { LogLevel, Outcome } from '@/lib/api/logs';
import { Search, X } from 'lucide-react';
import { useCallback, useState } from 'react';

export interface ActivityFilters {
	timeRange?: '15m' | '1h' | '6h' | '24h' | '7d';
	level?: LogLevel;
	outcome?: Outcome[];
	categories?: string[];
	q?: string;
}

interface ActivityFilterBarProps {
	onChange: (filters: ActivityFilters) => void;
	onTogglePauseTail?: (paused: boolean) => void;
	isPausedTail?: boolean;
	categories?: string[];
}

export function ActivityFilterBar({
	onChange,
	onTogglePauseTail,
	isPausedTail = false,
	categories = [],
}: ActivityFilterBarProps) {
	const [filters, setFilters] = useState<ActivityFilters>({
		timeRange: '1h',
		level: 'info',
		outcome: [],
		categories: [],
		q: '',
	});

	const [searchDebounce, setSearchDebounce] = useState<NodeJS.Timeout>();

	const handleChange = useCallback(
		(newFilters: ActivityFilters) => {
			setFilters(newFilters);
			onChange(newFilters);
		},
		[onChange],
	);

	const handleSearch = useCallback(
		(q: string) => {
			clearTimeout(searchDebounce);
			const timeout = setTimeout(() => {
				handleChange({ ...filters, q });
			}, 300);
			setSearchDebounce(timeout);
			setFilters(f => ({ ...f, q }));
		},
		[filters, handleChange, searchDebounce],
	);

	const toggleOutcome = (outcome: Outcome) => {
		const newOutcomes = filters.outcome || [];
		const idx = newOutcomes.indexOf(outcome);
		if (idx >= 0) {
			newOutcomes.splice(idx, 1);
		} else {
			newOutcomes.push(outcome);
		}
		handleChange({ ...filters, outcome: newOutcomes });
	};

	const removeCategory = (cat: string) => {
		const newCats = (filters.categories || []).filter(c => c !== cat);
		handleChange({ ...filters, categories: newCats });
	};

	const addCategory = (cat: string) => {
		const newCats = [...(filters.categories || [])];
		if (!newCats.includes(cat)) {
			newCats.push(cat);
		}
		handleChange({ ...filters, categories: newCats });
	};

	return (
		<div className="sticky top-0 z-10 border-b border-hairline bg-surface px-4 py-3 space-y-3">
			{/* Top row: Time + Level + Pause + Export */}
			<div className="flex items-center gap-2 flex-wrap">
				{/* Time range pills */}
				<div className="flex gap-1 items-center">
					{(['15m', '1h', '6h', '24h', '7d'] as const).map(tr => (
						<button
							key={tr}
							type="button"
							onClick={() => handleChange({ ...filters, timeRange: tr })}
							className={`px-2 py-1 rounded text-xs font-semibold transition-colors ${
								filters.timeRange === tr
									? 'bg-primary text-primary-fg'
									: 'bg-surface-2 hover:bg-surface-alt text-text-dim hover:text-text'
							}`}
						>
							{tr}
						</button>
					))}
				</div>

				{/* Level dropdown */}
				<select
					value={filters.level || 'info'}
					onChange={e => handleChange({ ...filters, level: e.target.value as LogLevel })}
					className="px-2 py-1 rounded text-xs bg-surface-2 border border-hairline text-text hover:bg-surface-alt transition-colors"
				>
					<option value="debug">Debug+</option>
					<option value="info">Info+</option>
					<option value="warn">Warn+</option>
					<option value="error">Error+</option>
					<option value="critical">Critical+</option>
				</select>

				{/* Outcome toggles */}
				<div className="flex gap-1 items-center ml-auto">
					<button
						type="button"
						onClick={() => toggleOutcome('success')}
						className={`px-2 py-1 rounded text-xs font-semibold transition-colors ${
							filters.outcome?.includes('success')
								? 'bg-ok/20 text-ok'
								: 'bg-surface-2 text-text-dim hover:bg-surface-alt hover:text-text'
						}`}
						title="Filter by success"
					>
						✓ Success
					</button>
					<button
						type="button"
						onClick={() => toggleOutcome('failure')}
						className={`px-2 py-1 rounded text-xs font-semibold transition-colors ${
							filters.outcome?.includes('failure')
								? 'bg-danger/20 text-danger'
								: 'bg-surface-2 text-text-dim hover:bg-surface-alt hover:text-text'
						}`}
						title="Filter by failure"
					>
						✗ Failure
					</button>
					<button
						type="button"
						onClick={() => toggleOutcome('unknown')}
						className={`px-2 py-1 rounded text-xs font-semibold transition-colors ${
							filters.outcome?.includes('unknown')
								? 'bg-warn/20 text-warn'
								: 'bg-surface-2 text-text-dim hover:bg-surface-alt hover:text-text'
						}`}
						title="Filter by unknown outcome"
					>
						◐ Unknown
					</button>
				</div>

				{/* Pause tail toggle */}
				<button
					type="button"
					onClick={() => onTogglePauseTail?.(!isPausedTail)}
					className={`px-2 py-1 rounded text-xs font-semibold transition-colors ${
						isPausedTail
							? 'bg-warn/10 text-warn'
							: 'bg-surface-2 text-ok hover:bg-surface-alt'
					}`}
					title={isPausedTail ? 'Resume live tail' : 'Pause live tail'}
				>
					{isPausedTail ? '⏸ Paused' : '◉ Live'}
				</button>
			</div>

			{/* Second row: Categories + Search */}
			<div className="flex items-center gap-2 flex-wrap">
				{/* Category chips */}
				<div className="flex gap-1 flex-wrap items-center">
					{filters.categories?.map(cat => (
						<button
							key={cat}
							type="button"
							onClick={() => removeCategory(cat)}
							className="px-2 py-1 rounded text-xs bg-accent/10 text-accent hover:bg-accent/20 transition-colors flex items-center gap-1"
						>
							{cat}
							<X size={12} />
						</button>
					))}
					{categories.length > 0 && (
						<select
							onChange={e => {
								if (e.target.value) {
									addCategory(e.target.value);
									e.target.value = '';
								}
							}}
							className="px-2 py-1 rounded text-xs bg-surface-2 border border-hairline text-text-dim hover:bg-surface-alt transition-colors"
							title="Add category filter"
						>
							<option value="">+ Add category</option>
							{categories
								.filter(c => !filters.categories?.includes(c))
								.map(cat => (
									<option key={cat} value={cat}>
										{cat}
									</option>
								))}
						</select>
					)}
				</div>

				{/* Search input */}
				<div className="flex items-center gap-1 ml-auto bg-surface-2 border border-hairline rounded px-2 py-1">
					<Search size={14} className="text-text-dim" />
					<input
						type="text"
						placeholder="Search…"
						value={filters.q || ''}
						onChange={e => handleSearch(e.target.value)}
						className="bg-transparent text-xs text-text placeholder:text-text-dim outline-none flex-1 max-w-xs"
					/>
				</div>
			</div>
		</div>
	);
}
