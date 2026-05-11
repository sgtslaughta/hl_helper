'use client';

import { HostTerminalPanel } from '@/components/hosts/host-terminal-panel';
import type { Host } from '@/lib/api/hosts';
import { ChevronsLeft, ChevronsRight, Maximize2, Minimize2, Pause, Play } from 'lucide-react';
import { useState } from 'react';
import { AgentConfig } from './agent-config';
import { HostFilesPanel } from './host-files-panel';
import { HostLogsPanel } from './host-logs-panel';
import { type PaneAction, PaneChrome, type PaneTab } from './pane-chrome';

interface UpdateAgentResponse {
	id?: string;
	version?: string;
}

export type ActionMode = 'term' | 'logs' | 'files' | 'trust' | 'agent';
export type PaneWidth = 'normal' | 'wide' | 'xwide';

const TABS: PaneTab[] = [
	{ key: 'term', label: 'Terminal', hotkey: 'w' },
	{ key: 'logs', label: 'Logs', hotkey: 'e' },
	{ key: 'files', label: 'Files', hotkey: 'r' },
	{ key: 'trust', label: 'Trust', hotkey: 't' },
	{ key: 'agent', label: 'Agent', hotkey: 'y' },
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
	const [updating, setUpdating] = useState(false);

	const handleUpdateAgent = async () => {
		try {
			setUpdating(true);
			const os = host.os || host.labels?.os;
			const arch = host.arch || host.labels?.arch;

			if (!os || !arch) {
				alert('Cannot determine host OS or architecture');
				return;
			}

			const latestR = await fetch(
				`/v1/agent-releases/latest?os=${encodeURIComponent(os)}&arch=${encodeURIComponent(arch)}`,
			);
			if (!latestR.ok) {
				alert('No latest release available for this host architecture');
				return;
			}
			const latest = (await latestR.json()) as UpdateAgentResponse;

			if (host.agent_version === latest.version) {
				alert('Already on latest version');
				return;
			}

			if (!confirm(`Update ${host.hostname} to ${latest.version}?`)) return;

			await fetch('/v1/tasks', {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({
					host_id: host.id,
					kind: 'agent_update',
					payload: { release_id: latest.id, force: false, reason: 'manual update' },
				}),
			});

			alert('Update task created');
		} catch (e) {
			const msg = e instanceof Error ? e.message : String(e);
			alert(`Error: ${msg}`);
		} finally {
			setUpdating(false);
		}
	};

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
			<div className="space-y-3">
				{mode === 'term' ? <HostTerminalPanel hostId={host.id} /> : null}
				{mode === 'logs' ? <HostLogsPanel hostId={host.id} paused={paused} /> : null}
				{mode === 'files' ? <HostFilesPanel hostId={host.id} /> : null}
				{mode === 'trust' ? (
					<div className="font-mono text-xs uppercase tracking-wider text-text-dim">
						Trust info for host {host.id}. Trust API not yet wired; placeholder pending backend
						endpoint.
					</div>
				) : null}
				{mode === 'agent' ? (
					<>
						<button
							type="button"
							onClick={handleUpdateAgent}
							disabled={updating}
							className="w-full rounded-sm border border-accent bg-accent/15 px-3 py-1.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-accent hover:bg-accent/25 disabled:cursor-not-allowed disabled:opacity-40"
						>
							{updating ? 'Updating…' : 'Update Agent'}
						</button>
						<AgentConfig host={host} />
					</>
				) : null}
			</div>
		</PaneChrome>
	);
}
