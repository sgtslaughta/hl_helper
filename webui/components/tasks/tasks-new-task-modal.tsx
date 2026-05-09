'use client';

import { ActionConfirmDialog } from '@/components/hosts/action-confirm-dialog';
import { ShellExecForm } from '@/components/hosts/shell-exec-form';
import { apiFetch } from '@/lib/api-client';
import { type Host, shellExecHost } from '@/lib/api/hosts';
import { useCanPerform } from '@/lib/rbac';
import * as Dialog from '@radix-ui/react-dialog';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Search, Server, X } from 'lucide-react';
import { useMemo, useState } from 'react';

interface Props {
	onClose: () => void;
}

export function TasksNewTaskModal({ onClose }: Props) {
	const cap = useCanPerform('shell-exec');
	const qc = useQueryClient();

	const [selected, setSelected] = useState<Host | null>(null);
	const [filter, setFilter] = useState('');

	const [command, setCommand] = useState('');
	const [timeoutS, setTimeoutS] = useState(60);
	const [asRoot, setAsRoot] = useState(false);
	const [reason, setReason] = useState('');

	const hostsQ = useQuery<Host[]>({
		queryKey: ['hosts'],
		queryFn: () => apiFetch<Host[]>('/v1/hosts'),
		staleTime: 30_000,
	});

	const filtered = useMemo(() => {
		const needle = filter.trim().toLowerCase();
		const list = hostsQ.data ?? [];
		if (!needle) return list;
		return list.filter(
			h =>
				h.hostname.toLowerCase().includes(needle) ||
				(h.display_name ?? '').toLowerCase().includes(needle) ||
				h.id.toLowerCase().includes(needle) ||
				Object.entries(h.labels ?? {}).some(
					([k, v]) => k.toLowerCase().includes(needle) || String(v).toLowerCase().includes(needle),
				),
		);
	}, [hostsQ.data, filter]);

	const shellMut = useMutation({
		mutationFn: (principal: string) => {
			if (!selected) throw new Error('no host');
			return shellExecHost(
				selected.id,
				{
					command,
					timeout_s: timeoutS,
					as_root: asRoot,
					reason: asRoot ? reason : undefined,
				},
				principal,
			);
		},
		onSuccess: () => {
			qc.invalidateQueries({ queryKey: ['tasks'] });
			if (selected) qc.invalidateQueries({ queryKey: ['hosts', selected.id, 'tasks'] });
			onClose();
		},
	});

	function dispatch() {
		shellMut.mutate(cap.principal ?? '');
	}

	// Stage 2: confirm dialog
	if (selected && cap.allowed) {
		return (
			<ActionConfirmDialog
				action="shell-exec"
				host={{ id: selected.id, hostname: selected.hostname, labels: selected.labels }}
				principal={cap.principal ?? ''}
				onClose={onClose}
				onConfirm={dispatch}
				formChildren={
					<>
						<div className="mb-3 rounded-sm border border-hairline bg-surface-2 px-2 py-1.5 text-xs">
							<button
								type="button"
								onClick={() => setSelected(null)}
								className="font-mono uppercase tracking-wider text-text-dim hover:text-accent"
							>
								← change host
							</button>
						</div>
						<ShellExecForm
							command={command}
							setCommand={setCommand}
							timeoutS={timeoutS}
							setTimeoutS={setTimeoutS}
							asRoot={asRoot}
							setAsRoot={setAsRoot}
							reason={reason}
							setReason={setReason}
						/>
					</>
				}
			/>
		);
	}

	// Stage 1: host picker
	return (
		<Dialog.Root open onOpenChange={o => !o && onClose()}>
			<Dialog.Portal>
				<Dialog.Overlay className="fixed inset-0 z-[90] bg-black/60 backdrop-blur-sm" />
				<Dialog.Content
					className="fixed left-1/2 top-1/2 z-[100] w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded border border-hairline bg-surface p-5 shadow-2xl"
					aria-describedby="task-host-pick-desc"
				>
					<div className="mb-3 flex items-center justify-between">
						<Dialog.Title className="font-mono text-sm font-semibold uppercase tracking-wider text-accent">
							New Task — Select Host
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
					<Dialog.Description id="task-host-pick-desc" className="mb-3 text-xs text-text-dim">
						Pick a host to dispatch this task to. Multi-host fan-out coming later.
					</Dialog.Description>

					{!cap.allowed ? (
						<div className="rounded-sm border border-danger/40 bg-danger/10 p-3 text-xs text-danger">
							{cap.reason ?? 'Shell exec capability required.'}
						</div>
					) : (
						<>
							<div className="relative mb-2">
								<Search
									size={11}
									className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-text-dim"
								/>
								<input
									type="text"
									value={filter}
									onChange={e => setFilter(e.target.value)}
									placeholder="Filter hosts (name / label)…"
									className="w-full rounded-sm border border-hairline bg-surface-2 py-1.5 pl-7 pr-2 font-mono text-xs text-text outline-none focus:border-accent"
								/>
							</div>

							<div className="max-h-72 overflow-auto rounded-sm border border-hairline">
								{hostsQ.isLoading ? (
									<div className="p-4 text-center font-mono text-[11px] uppercase tracking-wider text-text-dim">
										Loading…
									</div>
								) : filtered.length === 0 ? (
									<div className="p-4 text-center font-mono text-[11px] uppercase tracking-wider text-text-dim">
										No hosts match
									</div>
								) : (
									<ul>
										{filtered.map(h => (
											<li key={h.id}>
												<button
													type="button"
													onClick={() => setSelected(h)}
													className="flex w-full items-center gap-2 border-b border-hairline px-3 py-2 text-left font-mono text-xs hover:bg-surface-2 last:border-0"
												>
													<Server size={12} className="text-accent" />
													<span className="text-text">{h.hostname}</span>
													{h.display_name && h.display_name !== h.hostname ? (
														<span className="text-text-dim">({h.display_name})</span>
													) : null}
													<span
														className={`ml-auto mc-pip border-current px-1 py-0 text-[9px] ${
															h.status === 'healthy' || h.status === 'pending'
																? 'text-ok'
																: h.status === 'warning'
																	? 'text-warn'
																	: h.status === 'critical' || h.status === 'offline'
																		? 'text-danger'
																		: 'text-text-dim'
														}`}
													>
														{h.status}
													</span>
												</button>
											</li>
										))}
									</ul>
								)}
							</div>
						</>
					)}
				</Dialog.Content>
			</Dialog.Portal>
		</Dialog.Root>
	);
}
