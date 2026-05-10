'use client';

import { deletePolicy } from '@/lib/api/logs';
import { useState } from 'react';

export interface TempPolicyPillProps {
	hostId: string;
	expiresAt: string;
	onDeleted?: () => void;
}

export function TempPolicyPill({ hostId, expiresAt, onDeleted }: TempPolicyPillProps) {
	const [loading, setLoading] = useState(false);
	const [showConfirm, setShowConfirm] = useState(false);

	const expiresDate = new Date(expiresAt);
	const now = new Date();
	const remainingMs = expiresDate.getTime() - now.getTime();

	if (remainingMs <= 0) {
		return null;
	}

	const remainingSecs = Math.floor(remainingMs / 1000);
	const remainingMins = Math.floor(remainingSecs / 60);

	const label = remainingMins > 0 ? `${remainingMins}m` : `${remainingSecs}s`;

	const handleDelete = async () => {
		setLoading(true);
		try {
			await deletePolicy(`host:${hostId}`);
			onDeleted?.();
		} finally {
			setLoading(false);
			setShowConfirm(false);
		}
	};

	if (showConfirm) {
		return (
			// biome-ignore lint/a11y/useSemanticElements: native <dialog> requires showModal() and breaks Tailwind backdrop layout
			<div role="dialog" aria-modal="true" className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
				<div className="rounded border border-hairline bg-surface p-5 shadow-2xl max-w-sm">
					<h2 className="font-semibold text-text mb-2">Delete temporary log policy</h2>
					<p className="text-sm text-text-dim mb-4">
						Remove DEBUG-level policy from host {hostId.slice(0, 12)}. Are you sure?
					</p>
					<div className="flex justify-end gap-2">
						<button
							type="button"
							onClick={() => setShowConfirm(false)}
							className="px-3 py-1.5 rounded text-sm bg-surface-2 text-text hover:bg-surface-2/80"
						>
							Cancel
						</button>
						<button
							type="button"
							onClick={handleDelete}
							disabled={loading}
							className="px-3 py-1.5 rounded text-sm bg-danger text-danger-fg hover:bg-danger/90 disabled:opacity-50"
						>
							{loading ? 'Deleting…' : 'Delete'}
						</button>
					</div>
				</div>
			</div>
		);
	}

	return (
		<button
			type="button"
			onClick={() => setShowConfirm(true)}
			className="px-3 py-1 rounded text-xs font-semibold bg-warn/10 text-warn hover:bg-warn/20 transition-colors"
			disabled={loading}
		>
			DEBUG↑ {label}
		</button>
	);
}
