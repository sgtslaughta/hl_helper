'use client';

import * as Popover from '@radix-ui/react-popover';
import { Gauge, Pause, Play, Settings2 } from 'lucide-react';
import type { TickerPrefs, TickerSeverity, TickerSpeed, TickerType } from '@/lib/ticker-types';

const TYPES: TickerType[] = ['host', 'advisory', 'posture', 'task', 'audit', 'system'];
const SEVERITIES: TickerSeverity[] = ['info', 'ok', 'warn', 'error'];
const SPEEDS: TickerSpeed[] = ['slow', 'normal', 'fast'];

interface Props {
	prefs: TickerPrefs;
	onChange: (next: TickerPrefs) => void;
}

function toggleIn<T>(arr: T[], v: T): T[] {
	return arr.includes(v) ? arr.filter(x => x !== v) : [...arr, v];
}

function IconButton({
	children,
	onClick,
	ariaLabel,
	title,
	active,
}: {
	children: React.ReactNode;
	onClick?: () => void;
	ariaLabel: string;
	title?: string;
	active?: boolean;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			aria-label={ariaLabel}
			title={title ?? ariaLabel}
			className="inline-flex h-6 w-6 items-center justify-center rounded border border-transparent hover:border-hairline transition-colors"
			style={{ color: active ? 'var(--color-accent)' : 'var(--color-text-dim)' }}
		>
			{children}
		</button>
	);
}

export function TickerControls({ prefs, onChange }: Props) {
	return (
		<div className="flex items-center gap-1 px-2">
			<IconButton
				onClick={() => onChange({ ...prefs, paused: !prefs.paused })}
				ariaLabel={prefs.paused ? 'Resume ticker' : 'Pause ticker'}
				active={prefs.paused}
			>
				{prefs.paused ? <Play size={12} /> : <Pause size={12} />}
			</IconButton>

			<Popover.Root>
				<Popover.Trigger asChild>
					<button
						type="button"
						aria-label="Ticker settings"
						title="Ticker settings"
						className="inline-flex h-6 w-6 items-center justify-center rounded border border-transparent hover:border-hairline transition-colors"
						style={{ color: 'var(--color-text-dim)' }}
					>
						<Settings2 size={12} />
					</button>
				</Popover.Trigger>
				<Popover.Portal>
					<Popover.Content
						side="top"
						align="end"
						sideOffset={6}
						className="mc-bezel z-50 w-[260px] p-3 text-[11px] text-text"
					>
						<SectionLabel icon={<Gauge size={10} />} label="Speed" />
						<div className="flex gap-1 mb-3">
							{SPEEDS.map(s => (
								<button
									key={s}
									type="button"
									onClick={() => onChange({ ...prefs, speed: s })}
									className="mc-pip flex-1"
									style={{
										color:
											prefs.speed === s
												? 'var(--color-accent)'
												: 'var(--color-text-dim)',
										borderColor:
											prefs.speed === s
												? 'var(--color-accent)'
												: 'var(--color-text-dim)',
									}}
								>
									{s.toUpperCase()}
								</button>
							))}
						</div>

						<SectionLabel label="Types (none = all)" />
						<div className="flex flex-wrap gap-1 mb-3">
							{TYPES.map(t => {
								const on = prefs.types.includes(t);
								return (
									<button
										key={t}
										type="button"
										onClick={() =>
											onChange({ ...prefs, types: toggleIn(prefs.types, t) })
										}
										className="mc-pip"
										style={{
											color: on
												? 'var(--color-accent)'
												: 'var(--color-text-dim)',
											opacity: on ? 1 : 0.55,
										}}
									>
										{t}
									</button>
								);
							})}
						</div>

						<SectionLabel label="Severity (none = all)" />
						<div className="flex flex-wrap gap-1">
							{SEVERITIES.map(s => {
								const on = prefs.severities.includes(s);
								const color =
									s === 'error'
										? 'var(--color-danger)'
										: s === 'warn'
											? 'var(--color-warn)'
											: s === 'ok'
												? 'var(--color-ok)'
												: 'var(--color-accent)';
								return (
									<button
										key={s}
										type="button"
										onClick={() =>
											onChange({
												...prefs,
												severities: toggleIn(prefs.severities, s),
											})
										}
										className="mc-pip"
										style={{
											color,
											opacity: on ? 1 : 0.4,
										}}
									>
										{s}
									</button>
								);
							})}
						</div>
					</Popover.Content>
				</Popover.Portal>
			</Popover.Root>
		</div>
	);
}

function SectionLabel({ icon, label }: { icon?: React.ReactNode; label: string }) {
	return (
		<div className="mc-heading mb-1 flex items-center gap-1">
			{icon}
			<span>{label}</span>
		</div>
	);
}
