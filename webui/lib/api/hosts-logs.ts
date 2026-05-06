import { apiFetch } from '@/lib/api-client';

export interface LogLine {
	ts: string;
	level: 'info' | 'warn' | 'error';
	msg: string;
}

export function tailHostLogs(hostId: string, n = 200): Promise<LogLine[]> {
	return apiFetch<LogLine[]>(`/v1/hosts/${encodeURIComponent(hostId)}/logs?n=${n}`);
}
