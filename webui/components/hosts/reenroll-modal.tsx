'use client';

import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { mintReenrollToken, type ReenrollMint } from '@/lib/api/hosts';

export function ReenrollModal({
	hostId,
	onClose,
}: {
	hostId: string;
	onClose: () => void;
}) {
	const [minted, setMinted] = useState<ReenrollMint | null>(null);

	const mintMut = useMutation({
		mutationFn: () => mintReenrollToken(hostId),
		onSuccess: setMinted,
	});

	async function copy() {
		if (!minted) return;
		try {
			await navigator.clipboard.writeText(minted.install_command);
		} catch {
			// fallback for older browsers
			const ta = document.createElement('textarea');
			ta.value = minted.install_command;
			document.body.appendChild(ta);
			ta.select();
			document.execCommand('copy');
			ta.remove();
		}
	}

	return (
		<dialog
			open
			className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
		>
			<div
				className="w-full max-w-2xl rounded-lg border border-zinc-800 bg-zinc-950 p-6"
			>
				<header className="mb-4 flex items-center justify-between">
					<h2 className="text-lg font-semibold">Re-enroll host</h2>
					<button type="button" onClick={onClose} aria-label="Close" className="text-zinc-400 hover:text-zinc-200">
						✕
					</button>
				</header>

				<section className="mb-4 space-y-3 text-sm text-zinc-300">
					<p>
						<span className="font-semibold">Why re-enroll?</span> Use when agent signing key is
						destroyed, disk replaced, or rotation has failed past recovery. This issues a NEW host
						record; history is preserved under the same hostname but new host_id.
					</p>
					<p className="rounded bg-zinc-900 p-3 text-zinc-400">
						<span className="font-semibold text-amber-400">Auto-recovery first.</span> Healthy
						agents recover via signing-key challenge automatically. You only need this flow if
						status is Halted or after disk loss.
					</p>
				</section>

				{!minted ? (
					<button
						type="button"
						onClick={() => mintMut.mutate()}
						disabled={mintMut.isPending}
						className="rounded bg-amber-600 px-4 py-2 font-semibold text-black hover:bg-amber-500 disabled:opacity-40"
					>
						{mintMut.isPending ? 'Minting…' : 'Mint re-enrollment token'}
					</button>
				) : (
					<div className="space-y-3">
						<p className="text-sm text-zinc-400">
							Token expires {new Date(minted.expires_at).toLocaleString()} (one-time use).
						</p>
						<pre className="overflow-x-auto rounded border border-zinc-800 bg-black p-3 text-xs text-emerald-400">
{minted.install_command}
						</pre>
						<button
							type="button"
							onClick={copy}
							className="rounded border border-zinc-700 px-3 py-1 text-sm hover:bg-zinc-800"
						>
							Copy command
						</button>
					</div>
				)}
			</div>
		</dialog>
	);
}
