'use client';

import { Countdown } from '@/components/primitives/countdown';
import { Disclosure } from '@/components/primitives/disclosure';
import { RiskBadge } from '@/components/primitives/risk-badge';
import {
	type MintResponse,
	getAdvertisedOrigins,
	listPendingTokens,
	mintEnrollmentToken,
	revokePendingToken,
} from '@/lib/api/enrollment';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
	AlertTriangle,
	Check,
	ChevronRight,
	KeyRound,
	Server,
	ShieldAlert,
	Terminal as TerminalIcon,
	X as XIcon,
} from 'lucide-react';
import React, { useEffect, useState } from 'react';

interface Props {
	onClose: () => void;
}

type Step = 'mint' | 'install' | 'watching';

const TTL_OPTIONS: { label: string; value: number }[] = [
	{ label: '5 minutes', value: 300 },
	{ label: '15 minutes', value: 900 },
	{ label: '1 hour', value: 3600 },
	{ label: '24 hours', value: 86_400 },
];

export function EnrollmentModal({ onClose }: Props) {
	const qc = useQueryClient();
	const [step, setStep] = useState<Step>('mint');
	const [label, setLabel] = useState('');
	const [ttl, setTtl] = useState<number>(900);
	const [origin, setOrigin] = useState<string>('');
	const [minted, setMinted] = useState<MintResponse | null>(null);

	const originsQ = useQuery({
		queryKey: ['advertised-origins'],
		queryFn: getAdvertisedOrigins,
	});

	// Set default origin when data loads
	React.useEffect(() => {
		if (originsQ.data && !origin) {
			setOrigin(originsQ.data.default);
		}
	}, [originsQ.data, origin]);

	const mintMut = useMutation({
		mutationFn: () =>
			mintEnrollmentToken({
				label,
				ttl_seconds: ttl,
				origin: origin || undefined,
			}),
		onSuccess: data => {
			setMinted(data);
			setStep('install');
			qc.invalidateQueries({ queryKey: ['enrollment-tokens'] });
		},
	});

	const [revokeMsg, setRevokeMsg] = useState<{ tone: 'ok' | 'err'; text: string } | null>(
		null,
	);
	const revokeMut = useMutation({
		mutationFn: (tokenId: string) => revokePendingToken(tokenId),
		onSuccess: () => {
			qc.invalidateQueries({ queryKey: ['enrollment-tokens'] });
			setRevokeMsg({ tone: 'ok', text: 'Token revoked' });
			setTimeout(onClose, 900);
		},
		onError: e => {
			const detail = e instanceof Error ? e.message : 'Revoke failed';
			const text = /404|not_found/i.test(detail)
				? 'Token already revoked or not found'
				: detail;
			setRevokeMsg({ tone: 'err', text });
		},
	});

	useEffect(() => {
		function onKey(e: KeyboardEvent) {
			if (e.key === 'Escape') onClose();
		}
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	}, [onClose]);

	return (
		// biome-ignore lint/a11y/useSemanticElements: native <dialog> requires showModal() and breaks Tailwind backdrop layout
		<div
			role="dialog"
			aria-modal="true"
			className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
			onClick={onClose}
			onKeyDown={e => {
				if (e.key === 'Escape') onClose();
			}}
		>
			<div
				className="mc-bezel w-full max-w-2xl rounded-sm border border-hairline bg-surface p-5 shadow-2xl"
				onClick={e => e.stopPropagation()}
				onKeyDown={e => e.stopPropagation()}
			>
				<header className="mb-3 flex items-start justify-between gap-3 border-b border-hairline pb-3">
					<div className="min-w-0 flex-1">
						<h2 className="font-mono text-base font-semibold uppercase tracking-wider text-text">
							Enroll Host
						</h2>
						<p className="mt-1 font-mono text-[12px] text-text-dim">
							Mint a single-use token to register a new agent.
						</p>
					</div>
					<RiskBadge variant="caution" />
				</header>

				{step === 'mint' ? (
					<div className="space-y-3">
						<div className="rounded-sm border border-hairline bg-bezel/40 px-3 py-2 font-mono text-[12px] text-text-dim">
							Enrollment token authorizes one host to register itself. Treat as secret.
						</div>
						<label className="block font-mono text-[11px] uppercase tracking-wider text-text-dim">
							Label
							<input
								type="text"
								value={label}
								onChange={e => setLabel(e.target.value)}
								placeholder="lab-router-01"
								className="mt-1 w-full rounded-sm border border-hairline bg-canvas px-2 py-1.5 font-mono text-[13px] text-text outline-none focus:border-accent"
								aria-label="label"
							/>
						</label>
						<label className="block font-mono text-[11px] uppercase tracking-wider text-text-dim">
							Expires in
							<select
								value={ttl}
								onChange={e => setTtl(Number(e.target.value))}
								className="mt-1 w-full rounded-sm border border-hairline bg-canvas px-2 py-1.5 font-mono text-[13px] text-text outline-none focus:border-accent"
							>
								{TTL_OPTIONS.map(o => (
									<option key={o.value} value={o.value}>
										{o.label}
									</option>
								))}
							</select>
						</label>
						{(originsQ.data?.origins.length ?? 0) > 1 ? (
							<label className="block font-mono text-[11px] uppercase tracking-wider text-text-dim">
								Origin
								<select
									value={origin}
									onChange={e => setOrigin(e.target.value)}
									className="mt-1 w-full rounded-sm border border-hairline bg-canvas px-2 py-1.5 font-mono text-[13px] text-text outline-none focus:border-accent"
								>
									{originsQ.data?.origins.map(o => (
										<option key={o} value={o}>
											{o}
										</option>
									))}
								</select>
							</label>
						) : null}
						<Disclosure label="What is an enrollment token?" storageKey="enroll-explain">
							<ul className="space-y-1 font-mono text-[12px] text-text">
								<li className="flex items-start gap-2">
									<ChevronRight className="mt-0.5 shrink-0 text-accent" size={11} />
									<span>Single-use: redemption invalidates it.</span>
								</li>
								<li className="flex items-start gap-2">
									<ChevronRight className="mt-0.5 shrink-0 text-accent" size={11} />
									<span>Server stores only a hash; plaintext shown once.</span>
								</li>
								<li className="flex items-start gap-2">
									<ChevronRight className="mt-0.5 shrink-0 text-accent" size={11} />
									<span>Revoke at any time before redemption.</span>
								</li>
							</ul>
						</Disclosure>
						{mintMut.isError ? (
							<div className="flex items-start gap-2 rounded-sm border border-danger/40 bg-danger/10 px-3 py-2 font-mono text-[12px] text-danger">
								<ShieldAlert size={12} className="mt-0.5 shrink-0" />
								<span>
									{mintMut.error instanceof Error ? mintMut.error.message : 'Mint failed'}
								</span>
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
								disabled={label.trim().length === 0 || mintMut.isPending}
								onClick={() => mintMut.mutate()}
								className="rounded-sm border border-accent bg-accent/15 px-3 py-1.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-accent hover:bg-accent/25 disabled:cursor-not-allowed disabled:opacity-40"
							>
								{mintMut.isPending ? 'Minting…' : 'Mint Token'}
							</button>
						</footer>
					</div>
				) : null}

				{step === 'install' && minted ? (
					<InstallStep
						minted={minted}
						onDone={onClose}
						onRevoke={() => {
							setRevokeMsg(null);
							revokeMut.mutate(minted.token_id);
						}}
						onWatch={() => setStep('watching')}
						revokePending={revokeMut.isPending}
						revokeMsg={revokeMsg}
					/>
				) : null}

				{step === 'watching' && minted ? (
					<WatchingStep minted={minted} onClose={onClose} onBackToMint={() => setStep('mint')} />
				) : null}
			</div>
		</div>
	);
}

function InstallStep({
	minted,
	onDone,
	onRevoke,
	onWatch,
	revokePending,
	revokeMsg,
}: {
	minted: MintResponse;
	onDone: () => void;
	onRevoke: () => void;
	onWatch: () => void;
	revokePending: boolean;
	revokeMsg: { tone: 'ok' | 'err'; text: string } | null;
}) {
	async function copy() {
		const text = minted.install_command;
		try {
			if (navigator.clipboard && window.isSecureContext) {
				await navigator.clipboard.writeText(text);
				return;
			}
		} catch {
			// fall through to legacy path
		}
		// Legacy fallback for non-secure contexts (HTTP localhost on some browsers).
		const ta = document.createElement('textarea');
		ta.value = text;
		ta.style.position = 'fixed';
		ta.style.left = '-9999px';
		document.body.appendChild(ta);
		ta.select();
		try {
			document.execCommand('copy');
		} finally {
			document.body.removeChild(ta);
		}
	}
	const [copied, setCopied] = useState(false);
	async function doCopy() {
		await copy();
		setCopied(true);
		setTimeout(() => setCopied(false), 1500);
	}
	return (
		<div className="space-y-3">
			<div className="flex items-center gap-2 rounded-sm border border-hairline bg-bezel/40 px-3 py-2">
				<TerminalIcon className="text-accent" size={12} />
				<span className="font-mono text-[11px] uppercase tracking-wider text-text-dim">
					Run on target host
				</span>
			</div>
			<div className="relative rounded-sm border border-hairline bg-canvas p-2 pr-20 font-mono text-xs">
				<button
					type="button"
					onClick={doCopy}
					className="absolute right-1 top-1 rounded-sm border border-hairline bg-surface-2 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-text hover:border-accent"
				>
					{copied ? (
						<span className="flex items-center gap-1">
							<Check size={10} /> Copied
						</span>
					) : (
						'Copy'
					)}
				</button>
				<pre className="overflow-auto whitespace-pre-wrap break-all leading-relaxed text-text">
					{minted.install_command}
				</pre>
			</div>
			<div className="flex items-start gap-2 rounded-sm border border-warn/40 bg-warn/5 px-3 py-2 font-mono text-[12px] text-text">
				<AlertTriangle className="mc-caution-blink mt-0.5 shrink-0 text-warn" size={12} />
				<div>
					<span className="font-semibold uppercase tracking-wider text-warn">Requires sudo. </span>
					Installs agent to <code className="text-accent">/usr/local/bin</code>, writes sudoers
					entry at <code className="text-accent">/etc/sudoers.d/hl-agent</code>, registers systemd
					unit.
				</div>
			</div>
			<div className="flex items-center gap-1.5 rounded-sm border border-hairline bg-bezel/40 px-2.5 py-1.5">
				<Server className="text-text-dim" size={11} />
				<span className="font-mono text-[10px] uppercase tracking-wider text-text-dim">
					Expires in
				</span>
				<span className="mc-pip border-accent/40 text-accent">
					<Countdown to={minted.expires_at} />
				</span>
			</div>
			<Disclosure label="What this does" storageKey="enroll-what">
				<ul className="space-y-1 font-mono text-[12px] text-text">
					<li className="flex items-start gap-2">
						<ChevronRight className="mt-0.5 shrink-0 text-accent" size={11} />
						<span>Downloads agent binary signed by this server.</span>
					</li>
					<li className="flex items-start gap-2">
						<ChevronRight className="mt-0.5 shrink-0 text-accent" size={11} />
						<span>Generates Ed25519 keypair on host.</span>
					</li>
					<li className="flex items-start gap-2">
						<ChevronRight className="mt-0.5 shrink-0 text-accent" size={11} />
						<span>
							Submits CSR to <code className="text-accent">POST /v1/enroll</code>.
						</span>
					</li>
					<li className="flex items-start gap-2">
						<ChevronRight className="mt-0.5 shrink-0 text-accent" size={11} />
						<span>Server issues leaf cert; host appears in inventory.</span>
					</li>
				</ul>
			</Disclosure>
			<Disclosure label="Risks" storageKey="enroll-risks">
				<ul className="space-y-1 font-mono text-[12px] text-text">
					<li className="flex items-start gap-2">
						<ChevronRight className="mt-0.5 shrink-0 text-warn" size={11} />
						<span>Anyone holding token before expiry can enroll a host.</span>
					</li>
					<li className="flex items-start gap-2">
						<ChevronRight className="mt-0.5 shrink-0 text-warn" size={11} />
						<span>Revoke immediately if token is exposed.</span>
					</li>
					<li className="flex items-start gap-2">
						<ChevronRight className="mt-0.5 shrink-0 text-warn" size={11} />
						<span>Single-use; redemption invalidates it.</span>
					</li>
				</ul>
			</Disclosure>
			{revokeMsg ? (
				<div
					className={`flex items-center gap-2 rounded-sm border px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider ${
						revokeMsg.tone === 'ok'
							? 'border-ok/40 bg-ok/10 text-ok'
							: 'border-danger/40 bg-danger/10 text-danger'
					}`}
				>
					{revokeMsg.tone === 'ok' ? <Check size={11} /> : <ShieldAlert size={11} />}
					<span>{revokeMsg.text}</span>
				</div>
			) : null}
			<footer className="mt-4 flex justify-between gap-2 border-t border-hairline pt-3">
				<button
					type="button"
					onClick={onRevoke}
					disabled={revokePending || revokeMsg?.tone === 'ok'}
					className="rounded-sm border border-danger/40 bg-danger/5 px-3 py-1.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-danger hover:bg-danger/15 disabled:cursor-not-allowed disabled:opacity-40"
				>
					<KeyRound className="mr-1 inline" size={11} />
					{revokePending ? ' Revoking…' : ' Revoke'}
				</button>
				<div className="flex gap-2">
					<button
						type="button"
						onClick={onWatch}
						className="rounded-sm border border-hairline bg-surface-2 px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-text hover:border-accent"
					>
						Watch
					</button>
					<button
						type="button"
						onClick={onDone}
						className="rounded-sm border border-accent bg-accent/15 px-3 py-1.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-accent hover:bg-accent/25"
					>
						Done
					</button>
				</div>
			</footer>
		</div>
	);
}

type WatchingState = 'waiting' | 'enrolled' | 'expired';

function WatchingStep({
	minted,
	onClose,
	onBackToMint,
}: {
	minted: MintResponse;
	onClose: () => void;
	onBackToMint: () => void;
}) {
	const [watchingState, setWatchingState] = useState<WatchingState>('waiting');
	const expiresAt = new Date(minted.expires_at);

	const { data: pendingTokens } = useQuery({
		queryKey: ['enrollment-tokens'],
		queryFn: listPendingTokens,
		refetchInterval: 5000,
		enabled: watchingState === 'waiting',
	});

	const isTokenPending = pendingTokens?.some(t => t.id === minted.token_id) ?? true;
	const now = new Date();
	const isExpired = now >= expiresAt;

	React.useEffect(() => {
		if (watchingState === 'waiting') {
			if (isExpired) {
				setWatchingState('expired');
			} else if (!isTokenPending) {
				setWatchingState('enrolled');
			}
		}
	}, [isTokenPending, isExpired, watchingState]);

	const handleExpire = () => {
		setWatchingState('expired');
	};

	return (
		<div className="space-y-3">
			{watchingState === 'waiting' && (
				<>
					<div className="flex justify-center py-4">
						<div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
					</div>
					<p className="text-center font-mono text-[12px] uppercase tracking-wider text-text-dim">
						Waiting for agent…
					</p>
					<div className="flex justify-center">
						<span className="mc-pip border-accent/40 text-accent">
							<Countdown to={minted.expires_at} onExpire={handleExpire} />
						</span>
					</div>
				</>
			)}

			{watchingState === 'enrolled' && (
				<>
					<div className="flex flex-col items-center gap-2 py-4">
						<Check className="text-ok" size={32} strokeWidth={2.5} />
						<p className="font-mono text-[13px] font-semibold uppercase tracking-wider text-ok">
							Enrolled
						</p>
						<p className="font-mono text-[12px] text-text-dim">Host appeared in inventory.</p>
					</div>
					<footer className="mt-4 flex justify-end gap-2 border-t border-hairline pt-3">
						<button
							type="button"
							onClick={onClose}
							className="rounded-sm border border-accent bg-accent/15 px-3 py-1.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-accent hover:bg-accent/25"
						>
							Done
						</button>
					</footer>
				</>
			)}

			{watchingState === 'expired' && (
				<>
					<div className="flex flex-col items-center gap-2 py-4">
						<XIcon className="text-danger" size={32} strokeWidth={2.5} />
						<p className="font-mono text-[12px] uppercase tracking-wider text-danger">
							Token expired without redemption.
						</p>
					</div>
					<footer className="mt-4 flex justify-end gap-2 border-t border-hairline pt-3">
						<button
							type="button"
							onClick={onBackToMint}
							className="rounded-sm border border-hairline bg-surface-2 px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-text hover:border-accent"
						>
							Mint New
						</button>
						<button
							type="button"
							onClick={onClose}
							className="rounded-sm border border-accent bg-accent/15 px-3 py-1.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-accent hover:bg-accent/25"
						>
							Close
						</button>
					</footer>
				</>
			)}
		</div>
	);
}
