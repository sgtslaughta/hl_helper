'use client';

import { pruneStaleHosts } from '@/lib/api/hosts';
import { useCanPerform } from '@/lib/rbac';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
	AlertOctagon,
	CheckCircle2,
	HourglassIcon,
	PlugZap,
	PowerOff,
	Trash2,
	UserPlus,
} from 'lucide-react';
import type { ComponentType } from 'react';

export interface FleetCounts {
	critical: number;
	pending: number;
	online: number;
	offline: number;
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
	const pruneMut = useMutation({
		mutationFn: () => pruneStaleHosts(30, canDelete.principal),
		onSuccess: async data => {
			await qc.refetchQueries({ queryKey: ['hosts'], exact: true, type: 'active' });
			window.alert(`Pruned ${data.deleted} stale host(s).`);
		},
		onError: (err: Error) => window.alert(`Prune failed: ${err.message}`),
	});

	function onPrune() {
		if (
			!window.confirm(
				'Delete all hosts that never produced a heartbeat and were enrolled >30m ago?',
			)
		) {
			return;
		}
		pruneMut.mutate();
	}

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
				<button
					type="button"
					disabled={!canDelete.allowed || pruneMut.isPending}
					title={
						canDelete.allowed
							? 'Delete never-heartbeated hosts >30m old'
							: (canDelete.reason ?? 'Not allowed')
					}
					onClick={onPrune}
					className="flex items-center gap-1.5 rounded-sm border border-hairline bg-surface-2 px-2.5 py-1.5 font-mono text-[11px] uppercase tracking-wider text-text-dim transition-colors hover:border-warn hover:text-warn disabled:cursor-not-allowed disabled:opacity-40"
				>
					<Trash2 size={12} />
					{pruneMut.isPending ? 'Pruning…' : 'Prune Stale'}
				</button>
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
		</header>
	);
}
