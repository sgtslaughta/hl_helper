import { apiFetch } from '@/lib/api-client';

export interface Host {
  id: string;
  hostname: string;
  display_name: string | null;
  status: 'healthy' | 'warning' | 'critical' | 'offline' | 'pending';
  enrolled_at: string;
  last_seen_at: string | null;
  labels: Record<string, string>;
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

export interface RebootBody { delay_s: number; reason: string }
export interface ShellExecBody { command: string; timeout_s: number }
export interface PkgUpdateBody { classes: string[] }

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

export function rebootHost(id: string, body: RebootBody, principal: string): Promise<ActionResponse> {
  return action(id, 'reboot', body, principal);
}

export function shellExecHost(id: string, body: ShellExecBody, principal: string): Promise<ActionResponse> {
  return action(id, 'shell-exec', body, principal);
}

export function pkgUpdateHost(id: string, body: PkgUpdateBody, principal: string): Promise<ActionResponse> {
  return action(id, 'pkg-update', body, principal);
}

export function deleteHost(id: string, principal: string): Promise<void> {
  return apiFetch<void>(`/v1/hosts/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: { 'X-Acting-Principal': principal },
  });
}
