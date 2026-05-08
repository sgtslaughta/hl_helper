import { apiFetch } from '@/lib/api-client';

export interface HostSurvey {
	os: string;
	os_version: string;
	kernel: string;
	arch: string;
	virt: string;
	cpu_model: string;
	cpu_cores: number;
	cpu_threads: number;
	mem_total_bytes: number;
	disks: { device: string; mount: string; fstype: string; size_bytes: number }[];
	nics: { name: string; mac: string; ipv4: string[]; ipv6: string[]; speed_mbps: number }[];
	bios_vendor: string;
	bios_version: string;
	board_vendor: string;
	board_product: string;
	collected_at: string;
}

export interface HostMetrics {
	load_1: number;
	load_5: number;
	load_15: number;
	mem_used_pct: number;
	disk_used_pct: number;
	uptime_seconds: number;
	net_rx_bps?: number;
	net_tx_bps?: number;
}

export interface Host {
	id: string;
	hostname: string;
	display_name: string | null;
	status: 'healthy' | 'warning' | 'critical' | 'offline' | 'pending';
	enrolled_at: string;
	last_seen_at: string | null;
	labels: Record<string, string>;
	os?: string;
	os_version?: string;
	arch?: string;
	kernel?: string;
	cpu_pct?: number;
	mem_pct?: number;
	disk_pct?: number;
	uptime_s?: number;
	survey?: HostSurvey;
	survey_at?: string;
	metrics?: HostMetrics;
	metrics_at?: string;
	heartbeat_interval_s?: number;
	agent_version?: string;
}

export interface ActionResponse {
	task_id: string;
	dispatched: string[];
	denied: string[];
	pending_approval_ids: string[];
}

export function listHosts(params: { status?: string; search?: string } = {}): Promise<Host[]> {
	const q = new URLSearchParams();
	if (params.status && params.status !== 'all') q.set('status', params.status);
	if (params.search) q.set('search', params.search);
	const qs = q.toString();
	return apiFetch<Host[]>(`/v1/hosts${qs ? `?${qs}` : ''}`);
}

export function getHost(id: string): Promise<Host> {
	return apiFetch<Host>(`/v1/hosts/${encodeURIComponent(id)}`);
}

export interface RebootBody {
	delay_s: number;
	reason: string;
}
export interface ShellExecBody {
	command: string;
	timeout_s: number;
	as_root?: boolean;
	reason?: string;
}
export interface PkgUpdateBody {
	classes: string[];
}
export interface RevokeHostBody {
	reason: string;
}

function action<TBody extends object>(
	id: string,
	name: string,
	body: TBody,
	principal: string,
): Promise<ActionResponse> {
	return apiFetch<ActionResponse>(`/v1/hosts/${encodeURIComponent(id)}/actions/${name}`, {
		method: 'POST',
		body: JSON.stringify(body),
		headers: { 'X-Acting-Principal': principal },
	});
}

export function rebootHost(
	id: string,
	body: RebootBody,
	principal: string,
): Promise<ActionResponse> {
	return action(id, 'reboot', body, principal);
}

export function shellExecHost(
	id: string,
	body: ShellExecBody,
	principal: string,
): Promise<ActionResponse> {
	return action(id, 'shell-exec', body, principal);
}

export function pkgUpdateHost(
	id: string,
	body: PkgUpdateBody,
	principal: string,
): Promise<ActionResponse> {
	return action(id, 'pkg-update', body, principal);
}

export function revokeHostCert(
	id: string,
	body: RevokeHostBody,
	principal: string,
): Promise<ActionResponse> {
	return apiFetch<ActionResponse>(`/v1/hosts/${encodeURIComponent(id)}/revoke`, {
		method: 'POST',
		body: JSON.stringify(body),
		headers: { 'X-Acting-Principal': principal },
	});
}

export function deleteHost(id: string, principal: string): Promise<void> {
	return apiFetch<void>(`/v1/hosts/${encodeURIComponent(id)}`, {
		method: 'DELETE',
		headers: { 'X-Acting-Principal': principal },
	});
}

export function pruneStaleHosts(
	olderThanMinutes = 30,
	principal?: string,
): Promise<{ deleted: number }> {
	const headers: Record<string, string> = {};
	if (principal) headers['X-Acting-Principal'] = principal;
	return apiFetch<{ deleted: number }>(
		`/v1/hosts/prune-stale?older_than_minutes=${olderThanMinutes}`,
		{ method: 'POST', headers },
	);
}

export function resurveyHost(id: string): Promise<void> {
	return apiFetch<void>(`/v1/hosts/${encodeURIComponent(id)}/resurvey`, {
		method: 'POST',
	});
}

export function updateHeartbeatInterval(id: string, intervalS: number): Promise<Host> {
	return apiFetch<Host>(`/v1/hosts/${encodeURIComponent(id)}`, {
		method: 'PATCH',
		body: JSON.stringify({ heartbeat_interval_s: intervalS }),
	});
}
