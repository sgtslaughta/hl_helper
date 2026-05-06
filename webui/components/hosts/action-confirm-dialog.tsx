'use client';

import { Disclosure } from '@/components/primitives/disclosure';
import { RiskBadge } from '@/components/primitives/risk-badge';
import { TypedConfirmation } from '@/components/primitives/typed-confirmation';
import { type ActionType, riskCatalog } from '@/lib/risk-catalog';
import { type ReactNode, useState, useEffect } from 'react';

interface Props {
	action: ActionType;
	host: { id: string; hostname: string };
	principal: string;
	onConfirm: () => void;
	onClose: () => void;
	formChildren?: ReactNode;
}

export function ActionConfirmDialog({
	action,
	host,
	principal,
	onConfirm,
	onClose,
	formChildren,
}: Props) {
	const entry = riskCatalog[action];
	const [match, setMatch] = useState(false);
	const requiresType = entry.riskClass === 'irreversible';
	const canConfirm = !requiresType || match;

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
			className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
		>
			<div className="w-full max-w-lg rounded border border-hairline bg-surface p-5">
				<header className="mb-3 flex items-start justify-between gap-3">
					<div>
						<h2 className="text-h3 font-bold text-text">{entry.displayName}</h2>
						<p className="mt-1 text-sm text-text-dim">{entry.summary}</p>
					</div>
					<RiskBadge variant={entry.riskClass} />
				</header>

				<ul className="mb-3 list-disc space-y-1 pl-5 text-sm text-text">
					{entry.risks.map(r => (
						<li key={r}>{r}</li>
					))}
				</ul>

				{formChildren}

				<div className="space-y-2">
					<Disclosure label="Technical details" storageKey={`action-${action}-tech`}>
						<div className="space-y-1 font-mono text-xs">
							<div>
								<span className="text-text-dim">Method:</span> {entry.technical.method}
							</div>
							<div>
								<span className="text-text-dim">Path:</span> {path}
							</div>
							<div>
								<span className="text-text-dim">Payload preview:</span>
							</div>
							<pre className="overflow-auto rounded bg-surface-2 p-2">
								{JSON.stringify(entry.technical.samplePayload, null, 2)}
							</pre>
							<div>
								<span className="text-text-dim">Idempotency-Key:</span> generated per request (UUID
								v4)
							</div>
						</div>
					</Disclosure>
					<Disclosure label="What if this fails" storageKey={`action-${action}-rollback`}>
						<p className="text-sm">{entry.rollback}</p>
					</Disclosure>
				</div>

				<p className="mt-3 text-xs text-text-dim">
					Acting as <code className="text-text">{principal}</code> on host{' '}
					<code className="text-text">{host.hostname}</code>.
				</p>

				{requiresType ? (
					<div className="mt-3">
						<TypedConfirmation expected={host.hostname} onMatch={setMatch} />
					</div>
				) : null}

				<footer className="mt-4 flex justify-end gap-2">
					<button
						type="button"
						onClick={onClose}
						className="rounded border border-hairline px-3 py-1.5 text-sm text-text hover:bg-surface-2"
					>
						Cancel
					</button>
					<button
						type="button"
						disabled={!canConfirm}
						onClick={onConfirm}
						className="rounded bg-accent px-3 py-1.5 text-sm font-medium text-black disabled:cursor-not-allowed disabled:opacity-50"
					>
						Confirm
					</button>
				</footer>
			</div>
		</div>
	);
}
