'use client';

import { useFeedStatus, useTriggerFeedSync } from '@/lib/api/advisories-feeds';
import { AlertCircle, CheckCircle2, Loader2, RefreshCw } from 'lucide-react';

const FEED_LABELS: Record<string, string> = {
	osv: 'OSV (vulnerabilities)',
	epss: 'EPSS (exploit scores)',
	kev: 'CISA KEV (known-exploited)',
};

function formatRelative(iso: string | null): string {
	if (!iso) return 'never';
	const t = new Date(iso).getTime();
	const diff = Date.now() - t;
	if (diff < 0) return new Date(iso).toLocaleString();
	const mins = Math.floor(diff / 60_000);
	if (mins < 1) return 'just now';
	if (mins < 60) return `${mins}m ago`;
	const hrs = Math.floor(mins / 60);
	if (hrs < 24) return `${hrs}h ago`;
	const days = Math.floor(hrs / 24);
	return `${days}d ago`;
}

export function FeedHealthCard() {
	const q = useFeedStatus();
	const trigger = useTriggerFeedSync();

	const feeds = q.data?.feeds ?? [];

	return (
		<div className="rounded border border-hairline bg-surface p-4">
			<div className="mb-3 flex items-center justify-between">
				<div>
					<h3 className="text-h4 font-semibold text-text">Advisory feeds</h3>
					<p className="text-xs text-text-dim">
						Catalog sync status. Auto-refreshes every 30s.
					</p>
				</div>
				<button
					type="button"
					onClick={() => trigger.mutate('all')}
					disabled={trigger.isPending}
					className="inline-flex items-center gap-1 rounded border border-hairline bg-bg-2 px-3 py-1 font-mono text-xs text-text hover:bg-bg-3 disabled:opacity-50"
				>
					<RefreshCw className={`h-3 w-3 ${trigger.isPending ? 'animate-spin' : ''}`} />
					Resync all
				</button>
			</div>

			{q.isLoading ? (
				<div className="text-sm text-text-dim">…loading</div>
			) : feeds.length === 0 ? (
				<div className="text-sm text-text-dim">No feed data.</div>
			) : (
				<div className="space-y-2">
					{feeds.map(f => (
						<div
							key={f.feed}
							className="flex items-center justify-between gap-3 border-b border-hairline/50 pb-2 last:border-b-0 last:pb-0"
						>
							<div className="flex items-center gap-2 min-w-0">
								{f.last_error ? (
									<AlertCircle className="h-4 w-4 shrink-0 text-red-400" />
								) : f.in_progress ? (
									<Loader2 className="h-4 w-4 shrink-0 animate-spin text-blue-400" />
								) : f.last_sync_at ? (
									<CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
								) : (
									<AlertCircle className="h-4 w-4 shrink-0 text-text-dim" />
								)}
								<div className="min-w-0">
									<div className="text-sm text-text">
										{FEED_LABELS[f.feed] ?? f.feed}
									</div>
									<div className="truncate font-mono text-[11px] text-text-dim">
										synced {formatRelative(f.last_sync_at)} · {f.last_count.toLocaleString()} rows
										{f.last_error ? ` · err: ${f.last_error.slice(0, 80)}` : ''}
									</div>
								</div>
							</div>
							<button
								type="button"
								onClick={() =>
									trigger.mutate(f.feed as 'osv' | 'epss' | 'kev')
								}
								disabled={trigger.isPending || f.in_progress}
								className="rounded border border-hairline bg-bg-2 px-2 py-0.5 font-mono text-[11px] text-text hover:bg-bg-3 disabled:opacity-50"
							>
								{f.in_progress ? 'syncing…' : 'resync'}
							</button>
						</div>
					))}
				</div>
			)}
		</div>
	);
}
