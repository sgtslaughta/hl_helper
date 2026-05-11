'use client';

import type { LogLevel } from '@/lib/api/logs';
import { ChevronDown } from 'lucide-react';
import { useState } from 'react';

export interface LogFilters {
	timeRange?: { from: string; to: string };
	hosts?: string[];
	level?: LogLevel;
	categories?: string[];
	q?: string;
}

interface FilterRailProps {
	onChange: (filters: LogFilters) => void;
}

export function FilterRail({ onChange }: FilterRailProps) {
	const [filters, setFilters] = useState<LogFilters>({});
	const [expandedSection, setExpandedSection] = useState<string | null>('time-range');

	const handleChange = (newFilters: LogFilters) => {
		setFilters(newFilters);
		onChange(newFilters);
	};

	const toggleSection = (section: string) => {
		setExpandedSection(expandedSection === section ? null : section);
	};

	return (
		<div className="w-56 border-r border-hairline bg-surface-alt p-4 flex flex-col gap-6 overflow-y-auto">
			{/* Time Range */}
			<div>
				<button
					type="button"
					onClick={() => toggleSection('time-range')}
					className="flex items-center justify-between w-full text-sm font-semibold text-text hover:text-text-bright"
				>
					Time Range
					<ChevronDown
						size={16}
						className={`transition-transform ${expandedSection === 'time-range' ? 'rotate-180' : ''}`}
					/>
				</button>
				{expandedSection === 'time-range' && (
					<div className="mt-2 space-y-2">
						<div className="flex flex-col gap-1">
							<label htmlFor="from-input" className="text-xs text-text-dim">
								From
							</label>
							<input
								id="from-input"
								type="datetime-local"
								className="px-2 py-1 text-xs bg-surface border border-hairline rounded outline-none"
								onChange={e => {
									const from = e.target.value;
									handleChange({
										...filters,
										timeRange: { ...filters.timeRange, from } as unknown as {
											from: string;
											to: string;
										},
									});
								}}
							/>
						</div>
						<div className="flex flex-col gap-1">
							<label htmlFor="to-input" className="text-xs text-text-dim">
								To
							</label>
							<input
								id="to-input"
								type="datetime-local"
								className="px-2 py-1 text-xs bg-surface border border-hairline rounded outline-none"
								onChange={e => {
									const to = e.target.value;
									handleChange({
										...filters,
										timeRange: { ...filters.timeRange, to } as unknown as {
											from: string;
											to: string;
										},
									});
								}}
							/>
						</div>
					</div>
				)}
			</div>

			{/* Hosts */}
			<div>
				<button
					type="button"
					onClick={() => toggleSection('hosts')}
					className="flex items-center justify-between w-full text-sm font-semibold text-text hover:text-text-bright"
				>
					Hosts
					<ChevronDown
						size={16}
						className={`transition-transform ${expandedSection === 'hosts' ? 'rotate-180' : ''}`}
					/>
				</button>
				{expandedSection === 'hosts' && (
					<div className="mt-2">
						<input
							type="text"
							placeholder="Comma-separated hosts"
							className="w-full px-2 py-1 text-xs bg-surface border border-hairline rounded outline-none"
							onChange={e => {
								const hosts = e.target.value
									.split(',')
									.map(h => h.trim())
									.filter(Boolean);
								handleChange({ ...filters, hosts });
							}}
						/>
					</div>
				)}
			</div>

			{/* Level */}
			<div>
				<button
					type="button"
					onClick={() => toggleSection('level')}
					className="flex items-center justify-between w-full text-sm font-semibold text-text hover:text-text-bright"
				>
					Level
					<ChevronDown
						size={16}
						className={`transition-transform ${expandedSection === 'level' ? 'rotate-180' : ''}`}
					/>
				</button>
				{expandedSection === 'level' && (
					<div className="mt-2 space-y-1">
						{(['debug', 'info', 'warn', 'error', 'critical'] as const).map(level => (
							<div key={level}>
								<label className="flex items-center gap-2 text-xs text-text cursor-pointer hover:text-text-bright">
									<input
										type="radio"
										name="level"
										value={level}
										onChange={e => handleChange({ ...filters, level: e.target.value as LogLevel })}
									/>
									{level.charAt(0).toUpperCase() + level.slice(1)}
								</label>
							</div>
						))}
					</div>
				)}
			</div>

			{/* Categories */}
			<div>
				<button
					type="button"
					onClick={() => toggleSection('categories')}
					className="flex items-center justify-between w-full text-sm font-semibold text-text hover:text-text-bright"
				>
					Categories
					<ChevronDown
						size={16}
						className={`transition-transform ${expandedSection === 'categories' ? 'rotate-180' : ''}`}
					/>
				</button>
				{expandedSection === 'categories' && (
					<div className="mt-2">
						<input
							type="text"
							placeholder="Comma-separated categories"
							className="w-full px-2 py-1 text-xs bg-surface border border-hairline rounded outline-none"
							onChange={e => {
								const categories = e.target.value
									.split(',')
									.map(c => c.trim())
									.filter(Boolean);
								handleChange({ ...filters, categories });
							}}
						/>
					</div>
				)}
			</div>

			{/* Free-text Search */}
			<div>
				<button
					type="button"
					onClick={() => toggleSection('search')}
					className="flex items-center justify-between w-full text-sm font-semibold text-text hover:text-text-bright"
				>
					Search
					<ChevronDown
						size={16}
						className={`transition-transform ${expandedSection === 'search' ? 'rotate-180' : ''}`}
					/>
				</button>
				{expandedSection === 'search' && (
					<div className="mt-2">
						<input
							type="text"
							placeholder="Search message content"
							className="w-full px-2 py-1 text-xs bg-surface border border-hairline rounded outline-none"
							onChange={e => handleChange({ ...filters, q: e.target.value })}
						/>
					</div>
				)}
			</div>
		</div>
	);
}
