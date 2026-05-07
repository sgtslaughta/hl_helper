'use client';

import type { Host } from '@/lib/api/hosts';
import type { Density } from '@/lib/mission-control/density';
import { parseServerTime } from '@/lib/time';
import { AgentVersionChip } from '@/components/hosts/agent-version-chip';

interface Props {
	host: Host;
	density: Density;
	selected: boolean;
	onSelect: (id: string) => void;
	cpuHistory?: number[];
}

const DOT: Record<Host['status'], string> = {
	healthy: 'bg-green-500',
	warning: 'bg-yellow-500',
	critical: 'bg-red-500',
	offline: 'bg-text-dim',
	pending: 'bg-accent',
};

function Sparkline({ data, color }: { data: number[]; color: string }) {
	if (data.length < 2) return null;
	const max = Math.max(...data, 1);
	const points = data
		.map((v, i) => `${(i / (data.length - 1)) * 60},${18 - (v / max) * 16}`)
		.join(' ');
	return (
		<svg width="60" height="18" viewBox="0 0 60 18" aria-hidden="true">
			<title>CPU history sparkline</title>
			<polyline fill="none" stroke={color} strokeWidth="1" points={points} />
		</svg>
	);
}

function Bar({ pct, tone }: { pct: number; tone: 'ok' | 'warn' | 'crit' }) {
	const color = tone === 'crit' ? 'bg-red-500' : tone === 'warn' ? 'bg-yellow-500' : 'bg-green-500';
	return (
		<div className="h-[3px] flex-1 overflow-hidden rounded bg-surface-2">
			<div
				className={color}
				style={{ width: `${Math.min(100, Math.max(0, pct))}%`, height: '100%' }}
			/>
		</div>
	);
}

function tone(pct: number): 'ok' | 'warn' | 'crit' {
	if (pct >= 85) return 'crit';
	if (pct >= 70) return 'warn';
	return 'ok';
}

export function FleetRow({ host, density, selected, onSelect, cpuHistory }: Props) {
	const name = host.display_name ?? host.hostname;
	const dot = DOT[host.status];
	const isOffline = host.status === 'offline';

	// Prefer live heartbeat metrics over the legacy mock fields. cpu_pct is
	// derived from load_1 only when the agent reports it; we don't have a
	// directly-measured CPU percent yet, so fall back to memory pressure as a
	// rough load proxy for visual indication.
	const memPct = host.metrics?.mem_used_pct ?? host.mem_pct;
	const diskPct = host.metrics?.disk_used_pct;
	const load1 = host.metrics?.load_1;
	const osLabel = host.survey?.os ?? host.os;

	return (
		// biome-ignore lint/a11y/useSemanticElements: custom listbox item
		<button
			role="option"
			aria-selected={selected}
			onClick={() => onSelect(host.id)}
			className={`w-full cursor-pointer rounded px-2 py-1.5 text-sm text-left ${
				selected ? 'bg-accent/10 ring-1 ring-accent' : 'hover:bg-surface-2'
			}`}
			type="button"
		>
			<div className="flex items-center gap-2">
				<span className={`inline-block h-2 w-2 rounded-full ${dot}`} aria-hidden />
				<span className="truncate font-medium text-text">{name}</span>
				{density !== 'lean' && osLabel ? (
					<span className="rounded bg-surface-2 px-1.5 text-[10px] text-text-dim">{osLabel}</span>
				) : null}
				<AgentVersionChip current={host.agent_version} latest={host.agent_version_latest} status={host.agent_update_status} />
			</div>

			{density !== 'lean' ? (
				<div className="mt-1 font-mono text-[10px] text-text-dim">
					{isOffline
						? `offline · ${host.last_seen_at ? parseServerTime(host.last_seen_at).toLocaleTimeString() : 'never'}`
						: [
								load1 != null ? `ld ${load1.toFixed(2)}` : null,
								memPct != null ? `mem ${Math.round(memPct)}%` : null,
								diskPct != null ? `dsk ${Math.round(diskPct)}%` : null,
							]
								.filter(Boolean)
								.join(' · ') || 'no metrics'}
				</div>
			) : null}

			{density === 'balanced' && !isOffline && memPct != null ? (
				<div className="mt-1 flex gap-1">
					<Bar pct={memPct} tone={tone(memPct)} />
					{diskPct != null ? <Bar pct={diskPct} tone={tone(diskPct)} /> : null}
				</div>
			) : null}

			{density === 'rich' && cpuHistory && cpuHistory.length > 1 ? (
				<Sparkline data={cpuHistory} color="rgb(74 168 138)" />
			) : null}
		</button>
	);
}
