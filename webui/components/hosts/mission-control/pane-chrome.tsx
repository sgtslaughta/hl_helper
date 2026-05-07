'use client';

import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import * as Tooltip from '@radix-ui/react-tooltip';
import { ChevronDown } from 'lucide-react';
import type { ComponentType, ReactNode } from 'react';

export type PillTone = 'info' | 'warn' | 'crit' | 'ok';

export interface PaneTab {
	key: string;
	label: string;
	hotkey?: string;
	pill?: { text: string; tone: PillTone };
	overflow?: boolean;
	icon?: ComponentType<{ className?: string; size?: number }>;
}

export interface PaneAction {
	icon: ReactNode;
	label: string;
	onClick: () => void;
	disabled?: boolean;
}

interface Props {
	label: string;
	tabs: PaneTab[];
	value: string;
	onChange: (key: string) => void;
	actions: PaneAction[];
	children: ReactNode;
	/** When true, renders a static title instead of tabs (overview pane). */
	staticTitle?: string;
	/** Accent color override for the indicator bar (CSS color). */
	accent?: string;
}

const TONE_CLASS: Record<PillTone, string> = {
	info: 'bg-accent/20 text-accent',
	warn: 'bg-warn/20 text-warn',
	crit: 'bg-danger/20 text-danger',
	ok: 'bg-ok/20 text-ok',
};

function HotkeyBadge({ hotkey }: { hotkey: string }) {
	return (
		<kbd className="rounded-sm border border-hairline bg-bezel/60 px-1 font-mono text-[9px] text-text-dim">
			{hotkey}
		</kbd>
	);
}

export function PaneChrome({
	label,
	tabs,
	value,
	onChange,
	actions,
	children,
	staticTitle,
	accent,
}: Props) {
	const primary = tabs.filter(t => !t.overflow);
	const overflow = tabs.filter(t => t.overflow);
	const active = tabs.find(t => t.key === value);
	const activeOverflow = overflow.find(t => t.key === value);

	return (
		<section
			className="relative flex h-full flex-col rounded-sm border border-hairline bg-surface mc-bezel"
			aria-label={label}
		>
			<header
				className="flex items-center justify-between border-b border-hairline px-2"
				style={accent ? { boxShadow: `inset 0 2px 0 ${accent}` } : undefined}
			>
				<div role="tablist" className="flex items-center gap-0">
					{staticTitle ? (
						<div className="flex items-center gap-2 px-3 py-2">
							<span className="mc-led text-accent mc-led-pulse" aria-hidden />
							<span className="mc-heading">{staticTitle}</span>
						</div>
					) : (
						<Tooltip.Provider delayDuration={200}>
							{primary.map(t => {
								const Icon = t.icon;
								const isActive = value === t.key;
								return (
									<Tooltip.Root key={t.key}>
										<Tooltip.Trigger asChild>
											<button
												type="button"
												role="tab"
												aria-selected={isActive}
												onClick={() => onChange(t.key)}
												data-active={isActive}
												className="mc-tab"
											>
												{Icon ? <Icon size={13} /> : null}
												<span>{t.label}</span>
												{t.pill ? (
													<span
														data-tone={t.pill.tone}
														className={`mc-pip ${TONE_CLASS[t.pill.tone]} border-transparent`}
													>
														{t.pill.text}
													</span>
												) : null}
											</button>
										</Tooltip.Trigger>
										{t.hotkey ? (
											<Tooltip.Portal>
												<Tooltip.Content
													side="bottom"
													align="center"
													sideOffset={4}
													className="z-50 rounded-sm border border-hairline bg-surface-2 px-2 py-1 font-mono text-[10px] text-text-dim shadow-lg"
												>
													Press <HotkeyBadge hotkey={t.hotkey} /> to focus
													<Tooltip.Arrow className="fill-hairline" />
												</Tooltip.Content>
											</Tooltip.Portal>
										) : null}
									</Tooltip.Root>
								);
							})}
							{overflow.length > 0 ? (
								<DropdownMenu.Root>
									<DropdownMenu.Trigger asChild>
										<button
											type="button"
											className="mc-tab"
											data-active={!!activeOverflow}
											aria-label={
												activeOverflow ? `${activeOverflow.label} (more tabs)` : 'More tabs'
											}
										>
											<span>{activeOverflow ? activeOverflow.label : 'More'}</span>
											<ChevronDown size={11} />
										</button>
									</DropdownMenu.Trigger>
									<DropdownMenu.Content
										align="start"
										className="z-50 rounded-sm border border-hairline bg-surface-2 py-1 font-mono text-xs shadow-lg"
									>
										{overflow.map(t => (
											<DropdownMenu.Item
												key={t.key}
												onSelect={() => onChange(t.key)}
												className="cursor-pointer px-3 py-1.5 uppercase tracking-wider text-text-dim hover:bg-surface hover:text-text"
											>
												{t.label}
											</DropdownMenu.Item>
										))}
									</DropdownMenu.Content>
								</DropdownMenu.Root>
							) : null}
						</Tooltip.Provider>
					)}
				</div>
				<div className="flex items-center gap-1">
					{actions.map(a => (
						<button
							key={a.label}
							type="button"
							aria-label={a.label}
							title={a.label}
							disabled={a.disabled}
							onClick={a.onClick}
							className="flex h-7 w-7 items-center justify-center rounded-sm text-text-dim hover:bg-surface-2 hover:text-text disabled:opacity-40"
						>
							{a.icon}
						</button>
					))}
				</div>
			</header>
			<div role="tabpanel" aria-label={active?.label ?? label} className="flex-1 overflow-auto p-3">
				{children}
			</div>
		</section>
	);
}
