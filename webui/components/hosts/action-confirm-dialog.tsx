'use client';

import { RiskBadge } from '@/components/primitives/risk-badge';
import { TypedConfirmation } from '@/components/primitives/typed-confirmation';
import { useAuth } from '@/lib/auth';
import { type ActionType, riskCatalog } from '@/lib/risk-catalog';
import {
	AlertTriangle,
	ChevronDown,
	ChevronRight,
	KeyRound,
	Server,
	Terminal as TerminalIcon,
	User as UserIcon,
} from 'lucide-react';
import { type ReactNode, useEffect, useState } from 'react';

interface Props {
	action: ActionType;
	host: { id: string; hostname: string; labels?: Record<string, unknown> };
	principal: string;
	onConfirm: () => void;
	onClose: () => void;
	formChildren?: ReactNode;
	disableConfirm?: boolean;
}

function actorDisplay(user: ReturnType<typeof useAuth>['user'], fallbackId: string): string {
	if (!user) return fallbackId;
	return user.full_name || user.username || user.email || user.id;
}

function agentRunUser(host: Props['host']): string {
	const labels = host.labels ?? {};
	const v = labels.agent_user ?? labels.run_as ?? labels.process_user;
	if (typeof v === 'string' && v.length > 0) return v;
	return 'hl-agent';
}

function useTypewriter(text: string, speedMs = 18): string {
	const [out, setOut] = useState('');
	useEffect(() => {
		setOut('');
		let i = 0;
		const t = setInterval(() => {
			i += 1;
			setOut(text.slice(0, i));
			if (i >= text.length) clearInterval(t);
		}, speedMs);
		return () => clearInterval(t);
	}, [text, speedMs]);
	return out;
}

export function ActionConfirmDialog({
	action,
	host,
	principal,
	onConfirm,
	onClose,
	formChildren,
	disableConfirm,
}: Props) {
	const entry = riskCatalog[action];
	const [match, setMatch] = useState(false);
	const requiresType = entry.riskClass === 'irreversible';
	const canConfirm = !requiresType || match;
	const { user } = useAuth();
	const actor = actorDisplay(user, principal);
	const runAs = agentRunUser(host);
	const [cautionsOpen, setCautionsOpen] = useState(false);
	const [techOpen, setTechOpen] = useState(false);
	const [rollbackOpen, setRollbackOpen] = useState(false);

	const summary = useTypewriter(entry.summary, 16);
	const summaryDone = summary.length === entry.summary.length;

	useEffect(() => {
		function onKey(e: KeyboardEvent) {
			if (e.key === 'Escape') onClose();
		}
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	}, [onClose]);

	const path = entry.technical.pathTemplate.replace('{id}', host.id);

	return (
		// biome-ignore lint/a11y/useSemanticElements: native <dialog> requires showModal() and breaks Tailwind backdrop layout
		<div
			role="dialog"
			aria-modal="true"
			className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
		>
			<div className="mc-bezel w-full max-w-5xl rounded-sm border border-hairline bg-surface p-5 shadow-2xl">
				<header className="mb-3 flex items-start justify-between gap-3 border-b border-hairline pb-3">
					<div className="min-w-0 flex-1">
						<h2 className="font-mono text-base font-semibold uppercase tracking-wider text-text">
							{entry.displayName}
						</h2>
						<p
							className={`mt-1 min-h-[1.4em] font-mono text-[12px] text-text-dim ${
								summaryDone ? '' : 'mc-cursor'
							}`}
						>
							{summary}
						</p>
					</div>
				</header>

				{/* Risk badge as a single line above caution */}
				<div className="mb-2 flex justify-end">
					<RiskBadge variant={entry.riskClass} />
				</div>

				{/* Collapsed caution panel — only blinking icon visible until expanded */}
				<button
					type="button"
					onClick={() => setCautionsOpen(o => !o)}
					aria-expanded={cautionsOpen}
					className={`mb-4 flex w-full items-center gap-2 rounded-sm border border-warn/40 bg-warn/5 px-3 py-2 text-left transition-colors hover:bg-warn/10 ${
						cautionsOpen ? 'border-b-warn/60' : ''
					}`}
				>
					<AlertTriangle className="text-warn mc-caution-blink" size={14} />
					<span className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-warn">
						Cautions
					</span>
					<span className="font-mono text-[10px] text-text-dim">[{entry.risks.length}]</span>
					<span className="ml-auto">
						{cautionsOpen ? (
							<ChevronDown className="text-warn" size={12} />
						) : (
							<ChevronRight className="text-warn" size={12} />
						)}
					</span>
				</button>
				{cautionsOpen ? (
					<div className="-mt-3 mb-4 rounded-sm border border-warn/30 border-t-0 bg-warn/[0.03] px-3 py-2.5">
						<ul className="space-y-1.5 font-mono text-[12px] text-text">
							{entry.risks.map(r => (
								<li key={r} className="flex items-start gap-2">
									<ChevronRight className="mt-0.5 shrink-0 text-warn" size={11} />
									<span>{r}</span>
								</li>
							))}
						</ul>
					</div>
				) : null}

				{formChildren}

				<div className="space-y-2">
					<button
						type="button"
						onClick={() => setTechOpen(o => !o)}
						aria-expanded={techOpen}
						className="flex w-full items-center gap-2 rounded-sm border border-hairline bg-bezel/40 px-3 py-1.5 text-left hover:bg-surface-2"
					>
						<span className="mc-heading">Technical Details</span>
						<span className="ml-auto">
							{techOpen ? (
								<ChevronDown className="text-text-dim" size={12} />
							) : (
								<ChevronRight className="text-text-dim" size={12} />
							)}
						</span>
					</button>
					{techOpen ? (
						<div className="space-y-2 rounded-sm border border-hairline bg-bezel/40 p-2.5 font-mono text-[11px]">
							<div className="grid grid-cols-[80px_1fr] gap-2">
								<span className="font-semibold uppercase tracking-wider text-text-dim">Method</span>
								<span className="text-accent">{entry.technical.method}</span>
							</div>
							<div className="grid grid-cols-[80px_1fr] gap-2">
								<span className="font-semibold uppercase tracking-wider text-text-dim">Path</span>
								<code className="break-all text-text">{path}</code>
							</div>
							<div>
								<div className="mb-1 font-semibold uppercase tracking-wider text-text-dim">
									Payload preview
								</div>
								<pre className="overflow-auto rounded-sm border border-hairline bg-canvas p-2 text-[11px] text-text">
									{JSON.stringify(entry.technical.samplePayload, null, 2)}
								</pre>
							</div>
							<div className="grid grid-cols-[80px_1fr] gap-2">
								<span className="font-semibold uppercase tracking-wider text-text-dim">
									Idem-Key
								</span>
								<span className="text-text-dim">UUID v4 generated per request</span>
							</div>
						</div>
					) : null}

					<button
						type="button"
						onClick={() => setRollbackOpen(o => !o)}
						aria-expanded={rollbackOpen}
						className="flex w-full items-center gap-2 rounded-sm border border-hairline bg-bezel/40 px-3 py-1.5 text-left hover:bg-surface-2"
					>
						<span className="mc-heading">What if this fails</span>
						<span className="ml-auto">
							{rollbackOpen ? (
								<ChevronDown className="text-text-dim" size={12} />
							) : (
								<ChevronRight className="text-text-dim" size={12} />
							)}
						</span>
					</button>
					{rollbackOpen ? (
						<div className="rounded-sm border border-accent/30 bg-accent/5 px-3 py-2.5">
							<div className="mb-1.5 flex items-center gap-1.5">
								<KeyRound className="text-accent" size={11} />
								<span className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-accent">
									Rollback Plan
								</span>
							</div>
							<p className="font-mono text-[12px] leading-relaxed text-text">{entry.rollback}</p>
						</div>
					) : null}
				</div>

				{/* Actor / target / agent-user context strip */}
				<div className="mt-4 flex flex-wrap items-center gap-1.5 rounded-sm border border-hairline bg-bezel/40 px-2.5 py-1.5">
					<UserIcon className="text-accent" size={11} />
					<span className="font-mono text-[10px] uppercase tracking-wider text-text-dim">
						Acting as
					</span>
					<span className="mc-pip border-accent/40 text-accent">{actor}</span>
					<span className="mx-1 text-hairline">·</span>
					<Server className="text-text-dim" size={11} />
					<span className="font-mono text-[10px] uppercase tracking-wider text-text-dim">
						Target
					</span>
					<span className="mc-pip border-hairline text-text">{host.hostname}</span>
					<span className="mx-1 text-hairline">·</span>
					<TerminalIcon className="text-warn" size={11} />
					<span className="font-mono text-[10px] uppercase tracking-wider text-text-dim">
						Runs as
					</span>
					<span className="mc-pip border-warn/40 text-warn">{runAs}</span>
				</div>

				{requiresType ? (
					<div className="mt-3">
						<TypedConfirmation expected={host.hostname} onMatch={setMatch} />
					</div>
				) : null}

				<footer className="mt-4 flex justify-end gap-2 border-t border-hairline pt-3">
					<button
						type="button"
						onClick={onClose}
						className="rounded-sm border border-hairline bg-surface-2 px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-text hover:border-accent"
					>
						Cancel
					</button>
					<button
						type="button"
						disabled={!canConfirm || disableConfirm}
						onClick={onConfirm}
						className="rounded-sm border border-accent bg-accent/15 px-3 py-1.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-accent hover:bg-accent/25 disabled:cursor-not-allowed disabled:opacity-40"
					>
						Confirm
					</button>
				</footer>
			</div>
		</div>
	);
}
