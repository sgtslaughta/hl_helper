'use client';

import { pruneStaleHosts } from '@/lib/api/hosts';
import { useCanPerform } from '@/lib/rbac';
import * as Dialog from '@radix-ui/react-dialog';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
	AlertOctagon,
	CheckCircle2,
	HourglassIcon,
	PlugZap,
	PowerOff,
	Trash2,
	UserPlus,
	X,
} from 'lucide-react';
import type { ComponentType } from 'react';
import { useState } from 'react';

export interface FleetCounts {
	critical: number;
	pending: number;
	online: number;
	offline: number;
	stale: number;
}

interface Props {
	counts: FleetCounts;
	onEnroll: () => void;
	onPillClick?: (group: keyof FleetCounts) => void;
}

interface PipDef {
	key: keyof FleetCounts;
	label: string;
	color: string;
	icon: ComponentType<{ className?: string; size?: number }>;
	pulse?: boolean;
}

const PIPS: PipDef[] = [
	{ key: 'critical', label: 'CRIT', color: 'text-danger', icon: AlertOctagon, pulse: true },
	{ key: 'pending', label: 'PEND', color: 'text-warn', icon: HourglassIcon },
	{ key: 'online', label: 'ONLINE', color: 'text-ok', icon: CheckCircle2 },
	{ key: 'offline', label: 'OFFLINE', color: 'text-text-dim', icon: PowerOff },
];

export function TopBar({ counts, onEnroll, onPillClick }: Props) {
	const canMint = useCanPerform('mint-enrollment-token');
	const canDelete = useCanPerform('delete-host');
	const qc = useQueryClient();
	const [pruneOpen, setPruneOpen] = useState(false);
	const [pruneResult, setPruneResult] = useState<{ deleted: number } | null>(null);
	const [pruneError, setPruneError] = useState<string | null>(null);
	const pruneMut = useMutation({
		mutationFn: () => pruneStaleHosts(30, canDelete.principal),
		onSuccess: async data => {
			await qc.refetchQueries({ queryKey: ['hosts'], exact: true, type: 'active' });
			setPruneResult({ deleted: data.deleted });
			setPruneError(null);
		},
		onError: (err: Error) => {
			setPruneError(err.message);
			setPruneResult(null);
		},
	});

	function closePrune() {
		setPruneOpen(false);
		setPruneResult(null);
		setPruneError(null);
	}

	const showPrune = counts.stale > 0;

	return (
		<header className="relative flex items-center gap-3 rounded-sm border border-hairline bg-surface px-3 py-2 mc-bezel">
			{/* Brand block */}
			<div className="flex items-center gap-2">
				<PlugZap className="text-accent" size={18} aria-hidden />
				<div className="flex flex-col leading-none">
					<span className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-dim">
						Fleet
					</span>
					<h1 className="mc-readout text-base font-semibold text-text">HOSTS</h1>
				</div>
			</div>

			{/* Pips - only render when count > 0 */}
			<div className="flex items-center gap-1.5">
				{PIPS.map(p => {
					const n = counts[p.key];
					if (n === 0) return null;
					const Icon = p.icon;
					return (
						<button
							key={p.key}
							type="button"
							onClick={() => onPillClick?.(p.key)}
							title={`${n} ${p.label.toLowerCase()}`}
							className={`mc-pip ${p.color} hover:bg-surface-2`}
						>
							<Icon size={11} className={p.pulse && n > 0 ? 'mc-led-pulse' : ''} />
							<span className="mc-readout">{n}</span>
							<span className="opacity-70">{p.label}</span>
						</button>
					);
				})}
			</div>

			{/* Spacer */}
			<div className="flex-1" />

			{/* Action cluster */}
			<div className="flex items-center gap-1.5">
				{showPrune && (
					<button
						type="button"
						disabled={!canDelete.allowed || pruneMut.isPending}
						title={
							canDelete.allowed
								? `Delete ${counts.stale} never-heartbeated host(s) >30m old`
								: (canDelete.reason ?? 'Not allowed')
						}
						onClick={() => setPruneOpen(true)}
						className="flex items-center gap-1.5 rounded-sm border border-hairline bg-surface-2 px-2.5 py-1.5 font-mono text-[11px] uppercase tracking-wider text-warn transition-colors hover:border-warn disabled:cursor-not-allowed disabled:opacity-40"
					>
						<Trash2 size={12} />
						{pruneMut.isPending ? 'Pruning…' : `Prune Stale (${counts.stale})`}
					</button>
				)}
				<button
					type="button"
					disabled={!canMint.allowed}
					title={canMint.allowed ? 'Enroll host (⌘E)' : (canMint.reason ?? 'Not allowed')}
					onClick={onEnroll}
					className="flex items-center gap-1.5 rounded-sm border border-accent bg-accent/15 px-3 py-1.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-accent transition-all hover:bg-accent/25 hover:shadow-[0_0_14px_rgb(0_224_255_/_0.3)] disabled:cursor-not-allowed disabled:opacity-40"
				>
					<UserPlus size={13} />
					Enroll Host
				</button>
			</div>

			<Dialog.Root open={pruneOpen} onOpenChange={o => (o ? setPruneOpen(o) : closePrune())}>
				<Dialog.Portal>
					<Dialog.Overlay className="fixed inset-0 z-[90] bg-black/60 backdrop-blur-sm" />
					<Dialog.Content
						className="fixed left-1/2 top-1/2 z-[100] w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded border border-hairline bg-surface p-5 shadow-2xl"
						aria-describedby="prune-desc"
					>
						<div className="mb-3 flex items-center justify-between">
							<Dialog.Title className="font-mono text-sm font-semibold uppercase tracking-wider text-warn">
								Prune Stale Hosts
							</Dialog.Title>
							<Dialog.Close asChild>
								<button
									type="button"
									className="rounded p-1 text-text-dim hover:bg-surface-2 hover:text-text"
									aria-label="Close"
								>
									<X size={16} />
								</button>
							</Dialog.Close>
						</div>

						{pruneResult ? (
							<div className="space-y-3">
								<p className="text-sm text-text">
									Pruned <span className="font-mono text-ok">{pruneResult.deleted}</span> stale
									host(s).
								</p>
								<button
									type="button"
									onClick={closePrune}
									className="w-full rounded-sm border border-hairline bg-surface-2 px-3 py-2 font-mono text-xs uppercase tracking-wider text-text hover:bg-surface"
								>
									Done
								</button>
							</div>
						) : pruneError ? (
							<div className="space-y-3">
								<p className="text-sm text-danger">Prune failed: {pruneError}</p>
								<button
									type="button"
									onClick={closePrune}
									className="w-full rounded-sm border border-hairline bg-surface-2 px-3 py-2 font-mono text-xs uppercase tracking-wider text-text hover:bg-surface"
								>
									Close
								</button>
							</div>
						) : (
							<>
								<Dialog.Description id="prune-desc" className="mb-4 text-sm text-text-dim">
									Delete <span className="font-mono text-warn">{counts.stale}</span> host record(s)
									that have never produced a heartbeat and were enrolled more than 30 minutes ago?
									This cannot be undone.
								</Dialog.Description>
								<div className="flex justify-end gap-2">
									<button
										type="button"
										onClick={closePrune}
										className="rounded-sm border border-hairline bg-surface-2 px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-text-dim hover:text-text"
									>
										Cancel
									</button>
									<button
										type="button"
										onClick={() => pruneMut.mutate()}
										disabled={pruneMut.isPending}
										className="rounded-sm border border-warn bg-warn/15 px-3 py-1.5 font-mono text-xs font-semibold uppercase tracking-wider text-warn hover:bg-warn/25 disabled:opacity-40"
									>
										{pruneMut.isPending ? 'Pruning…' : 'Confirm Prune'}
									</button>
								</div>
							</>
						)}
					</Dialog.Content>
				</Dialog.Portal>
			</Dialog.Root>
		</header>
	);
}
