'use client';

import { apiFetch } from '@/lib/api-client';
import { type Host, listHosts } from '@/lib/api/hosts';
import { ignoreEventInInputs } from '@/lib/hotkeys';
import { usePaletteStore } from '@/stores/palette';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Boxes, ListChecks, ScrollText, Search, Server, X } from 'lucide-react';
import { useRouter } from 'next/navigation';
import type { ComponentType } from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useHotkeys } from 'react-hotkeys-hook';

interface TaskItem {
	id: string;
	kind: string;
	status: string;
	created_at: string;
	risk: string;
	summary?: string;
	host_id?: string;
}
interface AuditEntry {
	sequence: number;
	timestamp: string;
	actor: string;
	action: string;
	subject: string | null;
}
interface Finding {
	id: string;
	severity: string;
	title: string;
	subject_id: string | null;
	subject_kind: string;
}

interface ResultItem {
	kind: 'host' | 'task' | 'audit' | 'finding' | 'route';
	id: string;
	primary: string;
	secondary?: string;
	href: string;
}

const KIND_META: Record<
	ResultItem['kind'],
	{ icon: ComponentType<{ size?: number; className?: string }>; label: string; tone: string }
> = {
	host: { icon: Server, label: 'HOST', tone: 'text-accent' },
	task: { icon: ListChecks, label: 'TASK', tone: 'text-ok' },
	audit: { icon: ScrollText, label: 'AUDIT', tone: 'text-text-dim' },
	finding: { icon: AlertTriangle, label: 'POSTURE', tone: 'text-warn' },
	route: { icon: Boxes, label: 'PAGE', tone: 'text-text-dim' },
};

const ROUTES: { label: string; href: string }[] = [
	{ label: 'Hosts', href: '/hosts' },
	{ label: 'Containers', href: '/containers' },
	{ label: 'Topology', href: '/topology' },
	{ label: 'Tasks', href: '/tasks' },
	{ label: 'Updates', href: '/updates' },
	{ label: 'Approvals', href: '/approvals' },
	{ label: 'Schedules', href: '/schedules' },
	{ label: 'Audit', href: '/audit' },
	{ label: 'Posture', href: '/posture' },
	{ label: 'Secrets', href: '/secrets' },
	{ label: 'Webhooks', href: '/webhooks' },
	{ label: 'Plugins', href: '/plugins' },
	{ label: 'Integrations', href: '/integrations' },
	{ label: 'Security', href: '/security' },
	{ label: 'Settings', href: '/settings' },
];

function useDebounced<T>(value: T, ms: number): T {
	const [v, setV] = useState(value);
	useEffect(() => {
		const t = setTimeout(() => setV(value), ms);
		return () => clearTimeout(t);
	}, [value, ms]);
	return v;
}

function matches(query: string, ...fields: (string | null | undefined)[]): boolean {
	const q = query.toLowerCase().trim();
	if (!q) return false;
	return fields.some(f => (f ?? '').toLowerCase().includes(q));
}

export function CommandPalette() {
	const open = usePaletteStore(s => s.open);
	const setOpen = usePaletteStore(s => s.setOpen);
	const toggle = usePaletteStore(s => s.toggle);
	const router = useRouter();
	const [raw, setRaw] = useState('');
	const query = useDebounced(raw, 150);
	const inputRef = useRef<HTMLInputElement>(null);
	const [activeIdx, setActiveIdx] = useState(0);

	useHotkeys(
		'mod+k',
		e => {
			e.preventDefault();
			toggle();
		},
		{ ignoreEventWhen: ignoreEventInInputs },
	);

	useEffect(() => {
		if (open) inputRef.current?.focus();
		else setRaw('');
	}, [open]);

	const enabled = open && query.trim().length > 0;

	const hostsQ = useQuery<Host[]>({
		queryKey: ['palette', 'hosts'],
		queryFn: () => listHosts({}),
		enabled,
		staleTime: 10_000,
	});
	const tasksQ = useQuery<{ items: TaskItem[] }>({
		queryKey: ['palette', 'tasks'],
		queryFn: () => apiFetch('/v1/tasks?limit=200'),
		enabled,
		staleTime: 10_000,
	});
	const auditQ = useQuery<{ items: AuditEntry[] }>({
		queryKey: ['palette', 'audit'],
		queryFn: () => apiFetch('/v1/audit?limit=200'),
		enabled,
		staleTime: 10_000,
	});
	const postureQ = useQuery<{ findings: Finding[] }>({
		queryKey: ['palette', 'posture'],
		queryFn: () => apiFetch('/v1/posture'),
		enabled,
		staleTime: 10_000,
	});

	const results: ResultItem[] = useMemo(() => {
		if (!enabled) return [];
		const out: ResultItem[] = [];
		for (const r of ROUTES) {
			if (matches(query, r.label, r.href)) {
				out.push({ kind: 'route', id: r.href, primary: r.label, secondary: r.href, href: r.href });
			}
		}
		for (const h of hostsQ.data ?? []) {
			if (
				matches(
					query,
					h.hostname,
					h.display_name,
					h.id,
					h.os,
					h.arch,
					...Object.values(h.labels ?? {}).map(String),
				)
			) {
				out.push({
					kind: 'host',
					id: h.id,
					primary: h.display_name ?? h.hostname,
					secondary: `${h.id.slice(0, 12)} · ${h.status}`,
					href: `/hosts/${h.id}`,
				});
			}
		}
		for (const t of tasksQ.data?.items ?? []) {
			if (matches(query, t.summary, t.kind, t.status, t.id)) {
				out.push({
					kind: 'task',
					id: t.id,
					primary: t.summary ?? t.kind,
					secondary: `${t.id.slice(0, 8)} · ${t.status} · ${t.risk}`,
					href: `/tasks/${t.id}`,
				});
			}
		}
		for (const f of postureQ.data?.findings ?? []) {
			if (matches(query, f.title, f.severity, f.subject_id ?? '')) {
				out.push({
					kind: 'finding',
					id: f.id,
					primary: f.title,
					secondary: `${f.severity.toUpperCase()} · ${f.subject_kind}/${f.subject_id ?? '—'}`,
					href:
						f.subject_kind === 'host' && f.subject_id
							? `/hosts/${f.subject_id}`
							: `/posture/${f.id}`,
				});
			}
		}
		for (const e of auditQ.data?.items ?? []) {
			if (matches(query, e.actor, e.action, e.subject ?? '')) {
				out.push({
					kind: 'audit',
					id: String(e.sequence),
					primary: `${e.actor} ${e.action} ${e.subject ?? ''}`,
					secondary: `seq #${e.sequence} · ${new Date(e.timestamp).toLocaleString()}`,
					href: `/audit?seq=${e.sequence}`,
				});
			}
		}
		return out.slice(0, 50);
	}, [enabled, query, hostsQ.data, tasksQ.data, auditQ.data, postureQ.data]);

	useEffect(() => {
		setActiveIdx(0);
	}, []);

	function go(r: ResultItem) {
		router.push(r.href);
		setOpen(false);
	}

	function onKey(e: React.KeyboardEvent) {
		if (e.key === 'Escape') {
			e.preventDefault();
			setOpen(false);
			return;
		}
		if (e.key === 'ArrowDown') {
			e.preventDefault();
			setActiveIdx(i => Math.min(results.length - 1, i + 1));
			return;
		}
		if (e.key === 'ArrowUp') {
			e.preventDefault();
			setActiveIdx(i => Math.max(0, i - 1));
			return;
		}
		if (e.key === 'Enter' && results[activeIdx]) {
			e.preventDefault();
			go(results[activeIdx]);
		}
	}

	if (!open) return null;

	const isLoading =
		enabled && (hostsQ.isLoading || tasksQ.isLoading || auditQ.isLoading || postureQ.isLoading);

	const placeholder = enabled
		? 'Super search · hosts · tasks · audit · posture …'
		: 'Super search · type to scan the fleet · ⎋ close';

	return (
		// biome-ignore lint/a11y/useSemanticElements: native dialog incompatible with backdrop layout
		<div
			role="dialog"
			aria-modal="true"
			aria-label="Super search"
			className="fixed inset-0 z-[100] flex items-start justify-center bg-black/70 p-4 pt-[12vh]"
			onMouseDown={e => {
				if (e.target === e.currentTarget) setOpen(false);
			}}
		>
			<div className="mc-bezel w-full max-w-2xl rounded-sm border border-hairline bg-surface shadow-2xl">
				<div className="flex items-center gap-2 border-b border-hairline px-3 py-2.5">
					<Search className="text-accent" size={16} />
					<input
						ref={inputRef}
						value={raw}
						onChange={e => setRaw(e.target.value)}
						onKeyDown={onKey}
						placeholder={placeholder}
						className="flex-1 bg-transparent font-mono text-sm text-text outline-none placeholder:text-text-dim"
					/>
					{isLoading ? (
						<span className="font-mono text-[10px] uppercase tracking-wider text-accent">
							scanning…
						</span>
					) : null}
					<button
						type="button"
						onClick={() => setOpen(false)}
						aria-label="Close palette"
						className="rounded-sm p-1 text-text-dim hover:bg-surface-2 hover:text-text"
					>
						<X size={14} />
					</button>
				</div>

				<div className="max-h-[60vh] overflow-auto">
					{!enabled ? (
						<div className="p-3">
							<div className="mb-1.5 px-1 font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-accent">
								Quick Nav
							</div>
							{ROUTES.slice(0, 8).map(r => (
								<button
									type="button"
									key={r.href}
									onClick={() =>
										go({
											kind: 'route',
											id: r.href,
											primary: r.label,
											secondary: r.href,
											href: r.href,
										})
									}
									className="flex w-full items-center gap-3 rounded-sm px-2 py-1.5 text-left hover:bg-surface-2"
								>
									<Boxes className="text-text-dim" size={13} />
									<span className="font-mono text-[12px] text-text">{r.label}</span>
									<span className="ml-auto font-mono text-[10px] text-text-dim">{r.href}</span>
								</button>
							))}
						</div>
					) : results.length === 0 && !isLoading ? (
						<div className="px-3 py-8 text-center font-mono text-[11px] uppercase tracking-wider text-text-dim">
							No matches.
						</div>
					) : (
						<ul aria-label="Search results">
							{results.map((r, i) => {
								const meta = KIND_META[r.kind];
								const Icon = meta.icon;
								const active = i === activeIdx;
								return (
									<li key={`${r.kind}:${r.id}`}>
										<button
											type="button"
											aria-current={active ? 'true' : undefined}
											onMouseEnter={() => setActiveIdx(i)}
											onClick={() => go(r)}
											className={`flex w-full items-center gap-3 px-3 py-2 text-left transition-colors ${
												active
													? 'border-l-2 border-accent bg-accent/10'
													: 'border-l-2 border-transparent hover:bg-surface-2'
											}`}
										>
											<Icon size={14} className={meta.tone} />
											<span
												className={`mc-pip border-current ${meta.tone}`}
												style={{ padding: '2px 5px' }}
											>
												{meta.label}
											</span>
											<div className="min-w-0 flex-1">
												<div className="truncate font-mono text-[13px] text-text">{r.primary}</div>
												{r.secondary ? (
													<div className="truncate font-mono text-[10px] uppercase tracking-wider text-text-dim">
														{r.secondary}
													</div>
												) : null}
											</div>
										</button>
									</li>
								);
							})}
						</ul>
					)}
				</div>

				<div className="flex items-center justify-between border-t border-hairline px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-text-dim">
					<div className="flex items-center gap-3">
						<span>
							<kbd className="rounded-sm border border-hairline px-1">↑↓</kbd> nav
						</span>
						<span>
							<kbd className="rounded-sm border border-hairline px-1">↵</kbd> open
						</span>
						<span>
							<kbd className="rounded-sm border border-hairline px-1">esc</kbd> close
						</span>
					</div>
					<span>{enabled ? `${results.length} results` : `${ROUTES.length} routes`}</span>
				</div>
			</div>
		</div>
	);
}
