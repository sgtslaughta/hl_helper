'use client';

import { EnrollmentModal } from '@/components/hosts/enrollment-modal';
import { type PendingToken, listPendingTokens } from '@/lib/api/enrollment';
import { type Host, getHost, listHosts } from '@/lib/api/hosts';
import { isInputContext } from '@/lib/hotkeys';
import { useQuery } from '@tanstack/react-query';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { type ActionMode, ActionPane, type PaneWidth } from './action-pane';
import { FleetRail } from './fleet-rail';
import { FocusPane } from './focus-pane';
import type { FocusMode } from './overview-dashboard';
import { QuickActions } from './quick-actions';
import { type FleetCounts, TopBar } from './top-bar';

const FOCUS_KEYS: Record<string, FocusMode> = {
	'1': 'hardware',
	'2': 'tasks',
	'3': 'posture',
	'4': 'audit',
};
const ACTION_KEYS: Record<string, ActionMode> = {
	w: 'term',
	e: 'logs',
	r: 'files',
	t: 'trust',
};

export function MissionControlShell({ initialHostId }: { initialHostId: string | null }) {
	const router = useRouter();
	const pathname = usePathname();
	const [selectedId, setSelectedId] = useState<string | null>(initialHostId);
	const [focusMode, setFocusMode] = useState<FocusMode>('hardware');
	const [actionMode, setActionMode] = useState<ActionMode>('term');
	const [actionWidth, setActionWidth] = useState<PaneWidth>('normal');
	const [enrollOpen, setEnrollOpen] = useState(false);

	useEffect(() => {
		const target = selectedId ? `/hosts/${selectedId}` : '/hosts';
		if (pathname !== target) router.replace(target);
	}, [selectedId, pathname, router]);

	useEffect(() => {
		function onKey(e: KeyboardEvent) {
			// Use the shared input-context check so dialogs (e.g. shell-exec
			// command modal) suppress single-letter mode-switches while the
			// user is typing.
			if (isInputContext(e)) return;
			if (FOCUS_KEYS[e.key]) {
				e.preventDefault();
				setFocusMode(FOCUS_KEYS[e.key]);
				return;
			}
			if (ACTION_KEYS[e.key]) {
				e.preventDefault();
				setActionMode(ACTION_KEYS[e.key]);
				return;
			}
			if ((e.key === 'e' || e.key === 'E') && (e.metaKey || e.ctrlKey)) {
				e.preventDefault();
				setEnrollOpen(true);
			}
		}
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	}, []);

	useEffect(() => {
		if (selectedId) setFocusMode('hardware');
	}, [selectedId]);

	const hostsQ = useQuery<Host[]>({
		queryKey: ['hosts'],
		queryFn: () => listHosts({}),
		refetchInterval: 5_000,
		refetchIntervalInBackground: false,
	});
	const pendingQ = useQuery<PendingToken[]>({
		queryKey: ['enrollment-tokens'],
		queryFn: listPendingTokens,
		refetchInterval: 10_000,
	});
	const focusedQ = useQuery<Host>({
		queryKey: ['hosts', selectedId],
		queryFn: () => getHost(selectedId as string),
		enabled: !!selectedId,
		refetchInterval: 3_000,
	});

	const counts: FleetCounts = useMemo(() => {
		const out: FleetCounts = {
			critical: 0,
			pending: pendingQ.data?.length ?? 0,
			online: 0,
			offline: 0,
		};
		for (const h of hostsQ.data ?? []) {
			if (h.status === 'critical' || h.status === 'warning') out.critical++;
			else if (h.status === 'offline') out.offline++;
			else out.online++;
		}
		return out;
	}, [hostsQ.data, pendingQ.data]);

	return (
		<div className="flex h-[calc(100vh-3rem)] flex-col gap-2 p-2">
			<TopBar counts={counts} onEnroll={() => setEnrollOpen(true)} />
			<div className="flex flex-1 gap-2 overflow-hidden">
				{/* Left column: fleet list (scroll) + mission command (fixed) */}
				<div className="flex w-[280px] shrink-0 flex-col gap-2">
					<FleetRail selectedId={selectedId} onSelect={setSelectedId} />
					<section
						aria-label="Mission Command"
						className="mc-bezel shrink-0 rounded border border-hairline bg-surface p-2"
					>
						{focusedQ.data ? (
							<QuickActions host={focusedQ.data} onDeleted={() => setSelectedId(null)} />
						) : (
							<div className="flex flex-col items-start gap-1 px-1 py-2">
								<div className="flex items-center gap-1.5">
									<span className="mc-led text-text-dim" />
									<span className="mc-heading">Mission Command</span>
								</div>
								<p className="font-mono text-[10px] uppercase tracking-wider text-text-dim">
									Select host to arm controls.
								</p>
							</div>
						)}
					</section>
				</div>
				<div className="min-w-0 flex-1">
					{focusedQ.data ? (
						<FocusPane host={focusedQ.data} mode={focusMode} onModeChange={setFocusMode} />
					) : (
						<div className="flex h-full items-center justify-center rounded border border-hairline bg-surface text-text-dim">
							Select a host to focus.
						</div>
					)}
				</div>
				<div
					className="shrink-0 transition-[width] duration-200"
					style={{
						width: actionWidth === 'xwide' ? 760 : actionWidth === 'wide' ? 560 : 380,
					}}
				>
					{focusedQ.data ? (
						<ActionPane
							host={focusedQ.data}
							mode={actionMode}
							onModeChange={setActionMode}
							width={actionWidth}
							onWidthChange={setActionWidth}
						/>
					) : (
						<div className="flex h-full items-center justify-center rounded border border-hairline bg-surface text-text-dim">
							No host selected.
						</div>
					)}
				</div>
			</div>
			{enrollOpen ? <EnrollmentModal onClose={() => setEnrollOpen(false)} /> : null}
		</div>
	);
}
