'use client';

import { type PendingToken, listPendingTokens } from '@/lib/api/enrollment';
import { type Host, listHosts } from '@/lib/api/hosts';
import { isInputContext } from '@/lib/hotkeys';
import { useDensity } from '@/lib/mission-control/density';

/**
 * Substring match across hostname, display_name, id, OS/kernel/arch survey
 * fields, and label key/values. Supports `key:value` syntax to require both
 * sides match a single label entry; bare terms match anywhere. All
 * comparisons lowercased; `q` is already lowercased by the caller.
 */
function matchesFilter(h: Host, q: string): boolean {
	if (!q) return true;
	const labels = (h.labels ?? {}) as Record<string, unknown>;

	// `key:value` form requires a label whose key contains `key` AND whose
	// value contains `value`. Useful for narrowing to e.g. `env:prod`.
	const colon = q.indexOf(':');
	if (colon > 0 && colon < q.length - 1) {
		const k = q.slice(0, colon);
		const v = q.slice(colon + 1);
		for (const [lk, lv] of Object.entries(labels)) {
			if (lk.toLowerCase().includes(k) && String(lv).toLowerCase().includes(v)) {
				return true;
			}
		}
		// Also fall through to a plain substring match so users can keep
		// typing `:` mid-search without losing all results.
	}

	const parts: (string | null | undefined)[] = [
		h.hostname,
		h.display_name,
		h.id,
		h.survey?.os,
		h.survey?.os_version,
		h.survey?.kernel,
		h.survey?.arch,
		h.os,
		h.os_version,
		h.kernel,
		h.arch,
	];
	for (const [k, v] of Object.entries(labels)) {
		parts.push(k);
		parts.push(String(v));
		parts.push(`${k}=${v}`);
		parts.push(`${k}:${v}`);
	}
	const hay = parts.filter(Boolean).join(' ').toLowerCase();
	return hay.includes(q);
}
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { FleetRow } from './fleet-row';

interface Props {
	selectedId: string | null;
	onSelect: (id: string) => void;
	search?: string;
}

type Group = 'critical' | 'online' | 'pending' | 'offline';

const GROUP_ORDER: Group[] = ['critical', 'online', 'pending', 'offline'];
const GROUP_LABEL: Record<Group, string> = {
	critical: 'Critical',
	online: 'Online',
	pending: 'Pending',
	offline: 'Offline',
};

function groupOf(h: Host): Group {
	if (h.status === 'critical' || h.status === 'warning') return 'critical';
	if (h.status === 'offline') return 'offline';
	return 'online';
}

export function FleetRail({ selectedId, onSelect, search = '' }: Props) {
	const { density, cycle } = useDensity();
	const filterRef = useRef<HTMLInputElement>(null);
	const [collapsed, setCollapsed] = useState<Record<Group, boolean>>({
		critical: false,
		online: false,
		pending: false,
		offline: false,
	});
	const [filter, setFilter] = useState(search);

	const hostsQ = useQuery<Host[]>({ queryKey: ['hosts'], queryFn: () => listHosts({}) });
	const pendingQ = useQuery<PendingToken[]>({
		queryKey: ['enrollment-tokens'],
		queryFn: listPendingTokens,
		refetchInterval: 30_000,
	});

	const grouped = useMemo(() => {
		const out: Record<Group, Host[]> = { critical: [], online: [], pending: [], offline: [] };
		const q = filter.trim().toLowerCase();
		for (const h of hostsQ.data ?? []) {
			if (q && !matchesFilter(h, q)) continue;
			out[groupOf(h)].push(h);
		}
		return out;
	}, [hostsQ.data, filter]);

	useEffect(() => {
		function onKey(e: KeyboardEvent) {
			if (document.activeElement === filterRef.current) return;
			// Suppress while typing in any input or inside a modal dialog so
			// `/` and `j`/`k` don't get eaten when entering Unix paths or
			// command text.
			if (isInputContext(e)) return;
			if (e.key === '/') {
				e.preventDefault();
				filterRef.current?.focus();
				return;
			}
			const flat: Host[] = GROUP_ORDER.flatMap(g => (collapsed[g] ? [] : grouped[g]));
			if (flat.length === 0) return;
			const idx = flat.findIndex(h => h.id === selectedId);
			if (e.key === 'j') {
				e.preventDefault();
				onSelect(flat[Math.min(flat.length - 1, idx + 1)]?.id ?? flat[0].id);
			} else if (e.key === 'k') {
				e.preventDefault();
				onSelect(flat[Math.max(0, idx - 1)]?.id ?? flat[0].id);
			}
		}
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	}, [grouped, collapsed, selectedId, onSelect]);

	const pending = pendingQ.data ?? [];
	const counts: Record<Group, number> = {
		critical: grouped.critical.length,
		online: grouped.online.length,
		pending: pending.length,
		offline: grouped.offline.length,
	};

	return (
		<aside className="flex min-h-0 flex-1 flex-col rounded border border-hairline bg-surface mc-bezel">
			<div className="flex items-center gap-2 border-b border-hairline p-2">
				<input
					ref={filterRef}
					value={filter}
					onChange={e => setFilter(e.target.value)}
					placeholder="/  filter (host, label, key:value)…"
					className="flex-1 rounded bg-surface-2 px-2 py-1 text-sm text-text outline-none focus:ring-1 focus:ring-accent"
					aria-label="Filter hosts"
				/>
				<button
					type="button"
					aria-label={`Density: ${density}`}
					title={`Density: ${density} (click to cycle)`}
					onClick={cycle}
					className="rounded px-2 py-1 text-sm text-text-dim hover:bg-surface-2 hover:text-text"
				>
					≡
				</button>
			</div>
			{/* biome-ignore lint/a11y/useSemanticElements: custom collapsible grouped listbox */}
			<div className="flex-1 overflow-auto p-1" role="listbox" aria-label="Fleet" tabIndex={0}>
				{GROUP_ORDER.map(g => (
					<div key={g}>
						<button
							type="button"
							onClick={() => setCollapsed(c => ({ ...c, [g]: !c[g] }))}
							className="flex w-full items-center justify-between px-2 py-1 text-[10px] uppercase tracking-wide text-text-dim hover:text-text"
						>
							<span>
								{GROUP_LABEL[g]} · {counts[g]}
							</span>
							<span aria-hidden>{collapsed[g] ? '▸' : '▾'}</span>
						</button>
						{!collapsed[g]
							? g === 'pending'
								? pending.map(p => (
										<div key={p.id} className="px-2 py-1 text-xs text-text-dim">
											{p.label ?? p.id} (pending)
										</div>
									))
								: grouped[g].map(h => (
										<FleetRow
											key={h.id}
											host={h}
											density={density}
											selected={h.id === selectedId}
											onSelect={onSelect}
										/>
									))
							: null}
					</div>
				))}
				{hostsQ.isLoading ? <div className="p-2 text-xs text-text-dim">Loading…</div> : null}
			</div>
		</aside>
	);
}
