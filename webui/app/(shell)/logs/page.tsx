'use client';

export const dynamic = 'force-dynamic';

import { LogRow } from '@/components/hosts/activity/log-row';
import { listLogs, type LogRow as LogRowType } from '@/lib/api/logs';
import { useEffect, useState } from 'react';

export default function LogsHubPage() {
	const [rows, setRows] = useState<LogRowType[]>([]);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		(async () => {
			try {
				const resp = await listLogs({ limit: 50 });
				setRows(resp.items);
			} catch (e) {
				console.error('Failed to load logs', e);
			} finally {
				setLoading(false);
			}
		})();
	}, []);

	return (
		<div className="flex flex-col gap-4 p-6">
			<h1 className="text-h1 text-text">Logs Hub</h1>
			<p className="text-sm text-text-dim">Latest logs across all hosts</p>

			{loading && <div className="p-6 text-text-dim">Loading logs…</div>}

			{!loading && rows.length === 0 && <div className="p-6 text-text-dim">No logs found</div>}

			{!loading && rows.length > 0 && (
				<div className="border border-hairline rounded overflow-hidden">
					<div className="divide-y divide-hairline">
						{rows.map(row => (
							<LogRow key={`${row.id}-${row.seq}`} row={row} />
						))}
					</div>
				</div>
			)}
		</div>
	);
}
