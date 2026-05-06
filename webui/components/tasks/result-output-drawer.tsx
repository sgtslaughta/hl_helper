'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';

interface ResultDetail {
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
	onClose: () => void;
}

export function ResultOutputDrawer({ taskId, hostId, onClose }: Props) {
	const q = useQuery<ResultDetail>({
		queryKey: ['tasks', taskId, 'results', hostId],
		queryFn: () =>
			apiFetch<ResultDetail>(
				`/v1/tasks/${encodeURIComponent(taskId)}/results/${encodeURIComponent(hostId)}`,
			),
	});

	return (
		// biome-ignore lint/a11y/useSemanticElements: native <dialog> requires showModal()
		<div
			role="dialog"
			aria-modal="true"
			className="fixed inset-0 z-50 flex justify-end bg-black/60"
			onClick={onClose}
			onKeyDown={e => {
				if (e.key === 'Escape') onClose();
			}}
		>
			<div
				className="h-full w-full max-w-3xl overflow-y-auto border-l border-hairline bg-surface p-5"
				onClick={e => e.stopPropagation()}
				onKeyDown={e => e.stopPropagation()}
			>
				<header className="mb-3 flex items-start justify-between gap-3">
					<div>
						<h2 className="text-h3 font-bold text-text">Result output</h2>
						<p className="mt-1 font-mono text-xs text-text-dim">host: {hostId}</p>
					</div>
					<button
						type="button"
						onClick={onClose}
						className="rounded border border-hairline px-3 py-1.5 text-sm text-text hover:bg-surface-2"
					>
						Close
					</button>
				</header>

				{q.isLoading ? <BlueprintSkeleton rows={6} /> : null}
				{q.isError ? (
					<EmptyState
						title="Failed to load result"
						description="The result may not have arrived yet, or the agent rejected the command."
					/>
				) : null}

				{q.data ? (
					<div className="space-y-4">
						<div className="grid grid-cols-2 gap-2 rounded border border-hairline bg-surface-2 p-3 text-sm">
							<div className="text-text-dim">Status</div>
							<div className="text-text">{q.data.status}</div>
							<div className="text-text-dim">Exit code</div>
							<div className="text-text">{q.data.exit_code ?? '—'}</div>
							<div className="text-text-dim">Received</div>
							<div className="text-text font-mono text-xs">{q.data.received_at}</div>
							{q.data.rejection_reason ? (
								<>
									<div className="text-text-dim">Rejected</div>
									<div className="text-red-400">{q.data.rejection_reason}</div>
								</>
							) : null}
						</div>

						<OutputBlock
							label="stdout"
							text={q.data.stdout}
							truncated={q.data.stdout_truncated}
							empty="(no stdout)"
						/>
						<OutputBlock
							label="stderr"
							text={q.data.stderr}
							truncated={q.data.stderr_truncated}
							empty="(no stderr)"
							tone="error"
						/>
					</div>
				) : null}
			</div>
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
				<h3 className="text-sm font-semibold text-text">{label}</h3>
				{truncated ? (
					<span className="text-xs text-yellow-400">truncated at 64 KB</span>
				) : null}
			</div>
			<pre
				className={`max-h-96 overflow-auto whitespace-pre-wrap break-all rounded border border-hairline bg-surface-2 p-3 font-mono text-xs ${color}`}
			>
				{text || <span className="text-text-dim">{empty}</span>}
			</pre>
		</div>
	);
}
