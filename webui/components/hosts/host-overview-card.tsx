'use client';

import type { Host } from '@/lib/api/hosts';

export function HostOverviewCard({ host }: { host: Host }) {
	const fields: { k: string; v: string }[] = [
		{ k: 'Hostname', v: host.hostname },
		{ k: 'Display name', v: host.display_name ?? '—' },
		{ k: 'OS', v: host.labels?.os ?? '—' },
		{ k: 'Version', v: host.labels?.version ?? '—' },
		{ k: 'Agent version', v: host.labels?.agent_version ?? '—' },
		{ k: 'Enrolled at', v: host.enrolled_at },
		{ k: 'Last seen', v: host.last_seen_at ?? 'never' },
	];
	return (
		<div className="rounded border border-hairline bg-surface p-4">
			<h3 className="mb-3 text-h4 font-semibold text-text">Summary</h3>
			<dl className="grid grid-cols-2 gap-y-2 text-sm">
				{fields.map(f => (
					<div key={f.k} className="contents">
						<dt className="text-text-dim">{f.k}</dt>
						<dd className="text-text">{f.v}</dd>
					</div>
				))}
			</dl>
		</div>
	);
}
