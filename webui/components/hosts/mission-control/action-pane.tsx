'use client';

import { HostTerminalPanel } from '@/components/hosts/host-terminal-panel';
import type { Host } from '@/lib/api/hosts';
import {
	ChevronsLeft,
	ChevronsRight,
	Maximize2,
	Minimize2,
	Pause,
	Play,
	WrapText,
} from 'lucide-react';
import { useState } from 'react';
import { HostFilesPanel } from './host-files-panel';
import { HostLogsPanel } from './host-logs-panel';
import { type PaneAction, PaneChrome, type PaneTab } from './pane-chrome';

export type ActionMode = 'term' | 'logs' | 'files' | 'trust';
export type PaneWidth = 'normal' | 'wide' | 'xwide';

const TABS: PaneTab[] = [
	{ key: 'term', label: 'Terminal', hotkey: 'w' },
	{ key: 'logs', label: 'Logs', hotkey: 'e' },
	{ key: 'files', label: 'Files', hotkey: 'r' },
	{ key: 'trust', label: 'Trust', hotkey: 't' },
];

interface Props {
	host: Host;
	mode: ActionMode;
	onModeChange: (m: ActionMode) => void;
	width: PaneWidth;
	onWidthChange: (w: PaneWidth) => void;
}

const WIDTH_ORDER: PaneWidth[] = ['normal', 'wide', 'xwide'];

export function ActionPane({ host, mode, onModeChange, width, onWidthChange }: Props) {
	const [paused, setPaused] = useState(false);
	const [wrap, setWrap] = useState(true);

	const widthIdx = WIDTH_ORDER.indexOf(width);
	const canExpand = widthIdx < WIDTH_ORDER.length - 1;
	const canShrink = widthIdx > 0;

	const widthActions: PaneAction[] = [
		{
			icon: <ChevronsLeft size={13} />,
			label: canExpand ? `Expand left (${WIDTH_ORDER[widthIdx + 1]})` : 'Already widest',
			onClick: () => canExpand && onWidthChange(WIDTH_ORDER[widthIdx + 1]),
			disabled: !canExpand,
		},
		{
			icon: <ChevronsRight size={13} />,
			label: canShrink ? `Shrink (${WIDTH_ORDER[widthIdx - 1]})` : 'Already narrowest',
			onClick: () => canShrink && onWidthChange(WIDTH_ORDER[widthIdx - 1]),
			disabled: !canShrink,
		},
		{
			icon: width === 'normal' ? <Maximize2 size={13} /> : <Minimize2 size={13} />,
			label: width === 'normal' ? 'Maximize' : 'Reset width',
			onClick: () => onWidthChange(width === 'normal' ? 'xwide' : 'normal'),
		},
	];

	const logActions: PaneAction[] =
		mode === 'logs'
			? [
					{
						icon: paused ? <Play size={13} /> : <Pause size={13} />,
						label: paused ? 'Resume tail' : 'Pause tail',
						onClick: () => setPaused(p => !p),
					},
					{
						icon: <WrapText size={13} />,
						label: wrap ? 'Disable wrap' : 'Enable wrap',
						onClick: () => setWrap(w => !w),
					},
				]
			: [];

	const actions = [...logActions, ...widthActions];

	return (
		<PaneChrome
			label="Action"
			tabs={TABS}
			value={mode}
			onChange={k => onModeChange(k as ActionMode)}
			actions={actions}
		>
			{mode === 'term' ? <HostTerminalPanel hostId={host.id} /> : null}
			{mode === 'logs' ? (
				<HostLogsPanel hostId={host.id} paused={paused} wrap={wrap} severity="all" />
			) : null}
			{mode === 'files' ? <HostFilesPanel hostId={host.id} /> : null}
			{mode === 'trust' ? (
				<div className="font-mono text-xs uppercase tracking-wider text-text-dim">
					Trust info for host {host.id}. Trust API not yet wired; placeholder pending backend
					endpoint.
				</div>
			) : null}
		</PaneChrome>
	);
}
