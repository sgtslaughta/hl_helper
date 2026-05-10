// Compatibility shim: the legacy LogLine endpoint is replaced by /v1/logs.
// Existing callers should migrate to listLogs from './logs'.
import { listLogs, type LogRow } from './logs';

export interface LogLine {
	ts: string;
	level: 'info' | 'warn' | 'error';
	msg: string;
}

export async function tailHostLogs(hostId: string, n = 200): Promise<LogLine[]> {
	const resp = await listLogs({ hostId, limit: n });
	return resp.items.map((r: LogRow) => ({
		ts: r.ts,
		level: (r.level === 'debug' || r.level === 'critical' ? 'info' : r.level) as LogLine['level'],
		msg: r.message ?? r.action,
	}));
}
