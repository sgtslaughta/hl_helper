'use client';

import { useQuery } from '@tanstack/react-query';
import { type LogLine, tailHostLogs } from '@/lib/api/hosts-logs';

interface Props {
	hostId: string;
	paused: boolean;
	wrap: boolean;
	severity: 'all' | 'warn' | 'error';
}

const TONE: Record<LogLine['level'], string> = {
	info: 'text-text-dim',
	warn: 'text-yellow-300',
	error: 'text-red-300',
};

export function HostLogsPanel({ hostId, paused, wrap, severity }: Props) {
	const q = useQuery<LogLine[]>({
		queryKey: ['host-logs', hostId, severity],
		queryFn: () => tailHostLogs(hostId, 200),
		refetchInterval: paused ? false : 2_000,
		retry: false,
	});

	if (q.isError) {
		return (
			<div className="text-sm text-text-dim">
				Logs endpoint not available for this host.
			</div>
		);
	}

	const lines = (q.data ?? []).filter(l => severity === 'all' || l.level === severity);

	return (
		<div className={`font-mono text-[11px] ${wrap ? '' : 'whitespace-nowrap overflow-x-auto'}`}>
			{q.isLoading ? <div className="text-text-dim">Loading…</div> : null}
			{!q.isLoading && lines.length === 0 ? <div className="text-text-dim">No log lines.</div> : null}
			{lines.map((l, i) => (
				<div key={`${l.ts}-${i}`} className={`px-1 ${TONE[l.level]}`}>
					<span className="text-text-dim">{l.ts.slice(11, 19)}</span> {l.msg}
				</div>
			))}
		</div>
	);
}
