'use client';

import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { Fragment } from 'react';

export interface ResultDetail {
	host_id: string;
	command_id: string;
	status: string;
	exit_code: number | null;
	received_at: string;
	stdout: string;
	stdout_truncated: boolean;
	stderr: string;
	stderr_truncated: boolean;
	rejection_reason: string | null;
}

interface Props {
	taskId: string;
	hostId: string;
	// When provided, switches the preview into "inventory" mode (no
	// stdout/stderr; surface the synthesized summary as a clean key/value list).
	// Pass payload.action from the parent task row.
	taskAction?: string | null;
}

const STATUS_TONE: Record<string, string> = {
	ok: 'text-green-400',
	completed: 'text-green-400',
	succeeded: 'text-green-400',
	running: 'text-blue-400',
	pending: 'text-text-dim',
	failed: 'text-red-400',
	error: 'text-red-400',
	rejected: 'text-orange-400',
};

const INVENTORY_ACTIONS = new Set(['resurvey', 'rescan']);

export function TaskResultPreview({ taskId, hostId, taskAction }: Props) {
	const q = useQuery<ResultDetail>({
		queryKey: ['tasks', taskId, 'results', hostId],
		queryFn: () =>
			apiFetch<ResultDetail>(
				`/v1/tasks/${encodeURIComponent(taskId)}/results/${encodeURIComponent(hostId)}`,
			),
		refetchInterval: 5_000,
		retry: false,
	});

	const isInventory = taskAction != null && INVENTORY_ACTIONS.has(taskAction);

	if (q.isError) {
		return (
			<div className="flex items-center gap-3 rounded border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-300">
				Failed to load result
				<button
					type="button"
					onClick={() => q.refetch()}
					className="rounded border border-red-500/40 px-2 py-0.5 hover:bg-red-500/20"
				>
					Retry
				</button>
			</div>
		);
	}

	if (q.isLoading || !q.data) {
		return (
			<div className="space-y-1">
				<div className="h-3 w-1/3 rounded bg-surface-2" />
				<div className="h-3 w-2/3 rounded bg-surface-2" />
				<div className="h-3 w-1/2 rounded bg-surface-2" />
			</div>
		);
	}

	const d = q.data;
	const succeeded = d.status === 'ok' || d.status === 'completed' || d.status === 'succeeded';

	if (isInventory) {
		// Synthesized stdout from server is "key: value\n" lines for inventory tasks.
		const lines = (d.stdout || '')
			.split('\n')
			.map(l => l.trim())
			.filter(Boolean);
		const kv: Array<[string, string]> = [];
		let title = lines[0] || (succeeded ? 'Inventory collected' : 'Inventory failed');
		if (lines[0]?.includes(':')) title = succeeded ? 'Inventory collected' : 'Inventory failed';
		for (const line of lines) {
			const m = line.match(/^([^:]+):\s*(.*)$/);
			if (m) kv.push([m[1].trim(), m[2].trim()]);
		}

		return (
			<div className="space-y-2">
				<div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-xs">
					<span className={STATUS_TONE[d.status] ?? 'text-text-dim'}>
						{succeeded ? 'success' : d.status}
					</span>
					<span className="font-mono text-text-dim">{d.received_at}</span>
					<Link
						href={`/tasks/${taskId}`}
						className="ml-auto text-accent hover:underline"
						aria-label="Open full detail"
					>
						Open full detail →
					</Link>
				</div>
				<div className="rounded border border-hairline bg-surface-2 p-3">
					<div className="mb-2 font-mono text-xs uppercase tracking-wider text-text-dim">
						{title}
					</div>
					{kv.length === 0 ? (
						<div className="text-xs text-text-dim/60 italic">No summary available.</div>
					) : (
						<dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 font-mono text-xs">
							{kv.map(([k, v]) => (
								<Fragment key={k}>
									<dt className="text-text-dim uppercase tracking-wider">{k}</dt>
									<dd className="text-text">{v}</dd>
								</Fragment>
							))}
						</dl>
					)}
					{d.stderr ? <div className="mt-2 text-xs text-red-400">{d.stderr}</div> : null}
				</div>
			</div>
		);
	}

	return (
		<div className="space-y-3">
			<div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-xs">
				<span className={STATUS_TONE[d.status] ?? 'text-text-dim'}>{d.status}</span>
				<span className="text-text-dim">
					exit <span className="text-text">{d.exit_code ?? '—'}</span>
				</span>
				<span className="font-mono text-text-dim">{d.received_at}</span>
				{d.rejection_reason ? (
					<span className="text-orange-400">rejected: {d.rejection_reason}</span>
				) : null}
				<Link
					href={`/tasks/${taskId}`}
					className="ml-auto text-accent hover:underline"
					aria-label="Open full detail"
				>
					Open full detail →
				</Link>
			</div>
			<OutputBlock
				label="stdout"
				text={d.stdout}
				truncated={d.stdout_truncated}
				empty="(no stdout)"
			/>
			<OutputBlock
				label="stderr"
				text={d.stderr}
				truncated={d.stderr_truncated}
				empty="(no stderr)"
				tone="error"
			/>
		</div>
	);
}

function OutputBlock({
	label,
	text,
	truncated,
	empty,
	tone,
}: {
	label: string;
	text: string;
	truncated: boolean;
	empty: string;
	tone?: 'error';
}) {
	const color = tone === 'error' ? 'text-red-300' : 'text-text';
	return (
		<div>
			<div className="mb-1 flex items-baseline justify-between">
				<h4 className="text-xs font-semibold uppercase tracking-wide text-text-dim">{label}</h4>
				{truncated ? <span className="text-[10px] text-yellow-400">truncated at 64 KB</span> : null}
			</div>
			<pre
				className={`max-h-64 overflow-auto whitespace-pre-wrap break-all rounded border border-hairline bg-surface-2 p-2 font-mono text-[11px] ${color}`}
			>
				{text || <span className="text-text-dim">{empty}</span>}
			</pre>
		</div>
	);
}
