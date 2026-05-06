'use client';

import { type Host, listHosts, shellExecHost } from '@/lib/api/hosts';
import { useCanPerform } from '@/lib/rbac';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

interface Props {
	onClose: () => void;
}

export function NewTaskModal({ onClose }: Props) {
	const cap = useCanPerform('shell-exec');
	const qc = useQueryClient();
	const hostsQ = useQuery({ queryKey: ['hosts'], queryFn: () => listHosts() });
	const [hostId, setHostId] = useState('');
	const [command, setCommand] = useState('');
	const [timeoutS, setTimeoutS] = useState(60);
	const [result, setResult] = useState<string>('');

	const mut = useMutation({
		mutationFn: () => shellExecHost(hostId, { command, timeout_s: timeoutS }, cap.principal ?? ''),
		onSuccess: r => {
			qc.invalidateQueries({ queryKey: ['tasks'] });
			if (r.pending_approval_ids.length > 0) {
				setResult(`Task created — awaiting approval (id ${r.task_id.slice(0, 8)})`);
			} else if (r.dispatched.length > 0) {
				setResult(`Dispatched to ${r.dispatched.length} host(s) — task ${r.task_id.slice(0, 8)}`);
			} else {
				setResult(`Task ${r.task_id.slice(0, 8)} — denied=${r.denied.length}`);
			}
		},
		onError: e => setResult(`Error: ${(e as Error).message}`),
	});

	const hosts = (hostsQ.data ?? []).filter(h => h.status === 'healthy' || h.status === 'warning');

	return (
		// biome-ignore lint/a11y/useSemanticElements: native <dialog> requires showModal()
		<div
			role="dialog"
			aria-modal="true"
			className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
			onClick={onClose}
			onKeyDown={e => {
				if (e.key === 'Escape') onClose();
			}}
		>
			<div
				className="w-full max-w-lg rounded border border-hairline bg-surface p-5"
				onClick={e => e.stopPropagation()}
				onKeyDown={e => e.stopPropagation()}
			>
				<header className="mb-3 flex items-start justify-between">
					<h2 className="text-h3 font-bold text-text">New shell-exec task</h2>
					<button
						type="button"
						onClick={onClose}
						className="rounded border border-hairline px-2 py-1 text-sm text-text hover:bg-surface-2"
					>
						Close
					</button>
				</header>

				{!cap.allowed ? (
					<p className="text-sm text-red-400">{cap.reason}</p>
				) : (
					<>
						<div className="mb-3">
							<label htmlFor="nt-host" className="block text-sm font-medium text-text">
								Host
							</label>
							<select
								id="nt-host"
								value={hostId}
								onChange={e => setHostId(e.target.value)}
								className="mt-1 w-full rounded border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-text"
							>
								<option value="">Select a host…</option>
								{hosts.map((h: Host) => (
									<option key={h.id} value={h.id}>
										{h.hostname} ({h.status}) — {h.id.slice(0, 8)}
									</option>
								))}
							</select>
						</div>

						<div className="mb-3">
							<label htmlFor="nt-cmd" className="block text-sm font-medium text-text">
								Command
							</label>
							<input
								id="nt-cmd"
								type="text"
								value={command}
								onChange={e => setCommand(e.target.value)}
								className="mt-1 w-full rounded border border-hairline bg-surface-2 px-2 py-1.5 font-mono text-sm text-text"
								placeholder="echo hello && uname -a"
							/>
						</div>

						<div className="mb-4">
							<label htmlFor="nt-to" className="block text-sm font-medium text-text">
								Timeout (s)
							</label>
							<input
								id="nt-to"
								type="number"
								min="1"
								value={timeoutS}
								onChange={e => setTimeoutS(Math.max(1, Number.parseInt(e.target.value) || 1))}
								className="mt-1 w-32 rounded border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-text"
							/>
						</div>

						<div className="flex items-center gap-3">
							<button
								type="button"
								disabled={!hostId || !command || mut.isPending}
								onClick={() => mut.mutate()}
								className="rounded border border-hairline bg-accent px-3 py-1.5 text-sm font-medium text-text hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
							>
								{mut.isPending ? 'Dispatching…' : 'Dispatch'}
							</button>
							{result ? <span className="text-sm text-text-dim">{result}</span> : null}
						</div>
					</>
				)}
			</div>
		</div>
	);
}
