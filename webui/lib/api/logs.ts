'use client';

import { apiFetch } from '@/lib/api-client';

export type LogLevel = 'debug' | 'info' | 'warn' | 'error' | 'critical';
export type Outcome = 'success' | 'failure' | 'unknown';

export interface LogRow {
	id: number;
	host_id: string;
	agent_id: string;
	agent_session_id: string;
	agent_version?: string;
	seq: number;
	ts: string; // ISO
	level: LogLevel;
	action: string;
	category: string;
	outcome?: Outcome;
	duration_ns?: number;
	message?: string;
	labels: Record<string, string>;
	details: Record<string, unknown>;
	error?: { code?: string; message?: string; stack_trace?: string };
}

export interface ListLogsArgs {
	hostId?: string;
	hostIds?: string[];
	level?: LogLevel;
	categories?: string[];
	outcome?: Outcome;
	action?: string;
	q?: string;
	from?: string;
	to?: string;
	cursor?: string;
	limit?: number;
}

export interface FacetBucket {
	value: string;
	count: number;
}

export interface ListLogsResp {
	items: LogRow[];
	next_cursor: string | null;
	facets?: Record<string, FacetBucket[]>;
}

export interface CategoryRule {
	category: string;
	level?: LogLevel;
	sample_rate?: number;
	drop?: boolean;
}

export interface PolicyDoc {
	policy_version: number;
	default_level: LogLevel;
	batch_max_bytes: number;
	batch_max_interval_s: number;
	buffer_max_mb: number;
	buffer_max_days: number;
	default_sample_rate: number;
	categories: CategoryRule[];
	expires_at?: string | null;
	backoff_ms: number;
}

export async function listLogs(
	args: ListLogsArgs,
	fetcher: typeof apiFetch = apiFetch,
): Promise<ListLogsResp> {
	const p = new URLSearchParams();
	if (args.hostId) p.append('host_id', args.hostId);
	if (args.hostIds) {
		for (const h of args.hostIds) {
			p.append('host_id', h);
		}
	}
	if (args.level) p.set('level', args.level);
	if (args.categories) {
		for (const c of args.categories) {
			p.append('category', c);
		}
	}
	if (args.outcome) p.set('outcome', args.outcome);
	if (args.action) p.set('action', args.action);
	if (args.q) p.set('q', args.q);
	if (args.from) p.set('from', args.from);
	if (args.to) p.set('to', args.to);
	if (args.cursor) p.set('cursor', args.cursor);
	if (args.limit) p.set('limit', String(args.limit));
	return fetcher(`/v1/logs?${p.toString()}`);
}

export async function streamLogs(
	args: ListLogsArgs,
	onRow: (r: LogRow) => void,
): Promise<() => void> {
	const wsUrl = new URL('/ws/logs', globalThis.location?.origin || 'ws://localhost');
	const p = new URLSearchParams();
	if (args.hostId) p.append('host_id', args.hostId);
	if (args.hostIds) {
		for (const h of args.hostIds) {
			p.append('host_id', h);
		}
	}
	if (args.level) p.set('level', args.level);
	if (args.categories) {
		for (const c of args.categories) {
			p.append('category', c);
		}
	}
	if (args.outcome) p.set('outcome', args.outcome);
	if (args.action) p.set('action', args.action);
	if (args.q) p.set('q', args.q);
	if (args.from) p.set('from', args.from);
	if (args.to) p.set('to', args.to);

	wsUrl.search = p.toString();
	const ws = new WebSocket(wsUrl.toString());

	return () => {
		ws.close();
	};
}

export async function getPolicy(scope: string): Promise<PolicyDoc> {
	return apiFetch(`/v1/logs/policy/${encodeURIComponent(scope)}`);
}

export async function setPolicy(scope: string, body: Partial<PolicyDoc>): Promise<PolicyDoc> {
	return apiFetch(`/v1/logs/policy/${encodeURIComponent(scope)}`, {
		method: 'PATCH',
		body: JSON.stringify(body),
	});
}

export async function setHostPolicy(hostId: string, body: Partial<PolicyDoc>): Promise<PolicyDoc> {
	return apiFetch(`/v1/logs/policy/host/${encodeURIComponent(hostId)}`, {
		method: 'PATCH',
		body: JSON.stringify(body),
	});
}

export async function setTempPolicy(
	hostId: string,
	body: { level: LogLevel; categories: string[]; ttl_s: number },
): Promise<PolicyDoc> {
	return apiFetch(`/v1/logs/policy/host/${encodeURIComponent(hostId)}/temp`, {
		method: 'POST',
		body: JSON.stringify(body),
	});
}

export async function deletePolicy(scope: string): Promise<void> {
	await apiFetch(`/v1/logs/policy/${encodeURIComponent(scope)}`, {
		method: 'DELETE',
	});
}

export async function queryArchive(body: {
	from: string;
	to: string;
	host_ids?: string[];
	level?: LogLevel;
	action?: string;
	q?: string;
}): Promise<{ job_id: string; status: string }> {
	return apiFetch('/v1/logs/archive/query', {
		method: 'POST',
		body: JSON.stringify(body),
	});
}

export async function listCategories(): Promise<
	Array<{ name: string; description: string; default_level: string }>
> {
	return apiFetch('/v1/logs/categories');
}
