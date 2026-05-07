'use client';

import { HostAuditPanel } from '@/components/hosts/host-audit-panel';
import { HostPosturePanel } from '@/components/hosts/host-posture-panel';
import { HostTasksPanel } from '@/components/hosts/host-tasks-panel';
import type { Host } from '@/lib/api/hosts';
import {
	Activity,
	Cpu,
	FileText,
	ListChecks,
	ScrollText,
	ShieldCheck,
	Tag,
} from 'lucide-react';
import { AgentConfig } from './agent-config';
import { HardwarePanel } from './hardware-panel';
import { type FocusMode, OverviewDashboard } from './overview-dashboard';
import { PaneChrome, type PaneTab } from './pane-chrome';

const TABS: PaneTab[] = [
	{ key: 'hardware', label: 'Hardware', hotkey: '1', icon: Cpu },
	{ key: 'tasks', label: 'Tasks', hotkey: '2', icon: ListChecks },
	{ key: 'posture', label: 'Posture', hotkey: '3', icon: ShieldCheck },
	{ key: 'audit', label: 'Audit', hotkey: '4', icon: ScrollText },
	{ key: 'advisories', label: 'Advisories', overflow: true, icon: Activity },
	{ key: 'labels', label: 'Labels', overflow: true, icon: Tag },
	{ key: 'files', label: 'Files', overflow: true, icon: FileText },
];

interface Props {
	host: Host;
	mode: FocusMode;
	onModeChange: (m: FocusMode) => void;
}

const ACCENTS: Record<string, string> = {
	hardware: 'rgb(0 224 255)',
	posture: 'rgb(255 176 32)',
	audit: 'rgb(0 224 255)',
	tasks: 'rgb(57 217 138)',
	advisories: 'rgb(255 92 92)',
	labels: 'rgb(0 224 255)',
	files: 'rgb(0 224 255)',
};

export function FocusPane({ host, mode, onModeChange }: Props) {
	const tabMode = mode === 'overview' ? 'hardware' : mode;
	const accent = ACCENTS[tabMode] ?? 'rgb(0 224 255)';

	return (
		<div className="flex h-full flex-col gap-2">
			{/* Static overview pane (no tabs, always visible) */}
			<div className="flex-shrink-0">
				<PaneChrome
					label="Overview"
					tabs={[]}
					value=""
					onChange={() => {}}
					actions={[]}
					staticTitle="OVERVIEW"
				>
					<OverviewDashboard host={host} onJump={onModeChange} />
				</PaneChrome>
			</div>
			{/* Tabbed sub-pane for everything else */}
			<div className="min-h-0 flex-1">
				<PaneChrome
					label="Detail"
					tabs={TABS}
					value={tabMode}
					onChange={k => onModeChange(k as FocusMode)}
					actions={[]}
					accent={accent}
				>
					{tabMode === 'hardware' ? (
						<div className="flex flex-col gap-3">
							<HardwarePanel host={host} />
							<AgentConfig host={host} />
						</div>
					) : null}
					{tabMode === 'posture' ? <HostPosturePanel hostId={host.id} /> : null}
					{tabMode === 'audit' ? <HostAuditPanel hostId={host.id} /> : null}
					{tabMode === 'tasks' ? <HostTasksPanel hostId={host.id} host={host} /> : null}
					{tabMode === 'advisories' || tabMode === 'labels' || tabMode === 'files' ? (
						<div className="font-mono text-xs uppercase tracking-wider text-text-dim">
							{tabMode} view (placeholder).
						</div>
					) : null}
				</PaneChrome>
			</div>
		</div>
	);
}
