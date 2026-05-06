'use client';

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';
import type { Host } from '@/lib/api/hosts';

export type FocusMode =
  | 'overview'
  | 'posture'
  | 'audit'
  | 'tasks'
  | 'advisories'
  | 'labels'
  | 'files'
  | 'network'
  | 'updates';

interface Props {
  host: Host;
  onJump: (mode: FocusMode) => void;
}

interface TaskItem {
  id: string;
  kind: string;
  status: string;
  created_at: string;
  risk: string;
  summary?: string;
}

interface TasksPage {
  items: TaskItem[];
  next_cursor: string | null;
}

interface AuditEntry {
  sequence: number;
  timestamp: string;
  actor: string;
  action: string;
  subject: string | null;
  payload: Record<string, unknown>;
  prev_hash: string;
  entry_hash: string;
}

interface AuditPage {
  items: AuditEntry[];
  next_cursor: string | null;
}

interface Finding {
  id: string;
  severity: string;
  title: string;
  summary: string;
  fix_action_url: string | null;
  docs_url: string | null;
  rule: string;
  subject_kind: string;
  subject_id: string | null;
  first_seen: string | null;
  last_seen: string | null;
  suppressed_until: string | null;
}

interface PostureResponse {
  findings: Finding[];
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded border border-hairline bg-surface-2 p-2">
      <div className="text-[10px] uppercase tracking-wide text-text-dim">{label}</div>
      <div className="text-lg font-semibold text-text">{value}</div>
      {sub ? <div className="text-[10px] text-text-dim">{sub}</div> : null}
    </div>
  );
}

function SectionHeader({
  title,
  onJump,
  jumpLabel,
}: {
  title: string;
  onJump?: () => void;
  jumpLabel?: string;
}) {
  return (
    <div className="mt-3 mb-1 flex items-baseline justify-between">
      <h4 className="text-[10px] uppercase tracking-wide text-accent">{title}</h4>
      {onJump ? (
        <button
          type="button"
          aria-label={`jump to ${jumpLabel ?? title}`}
          onClick={onJump}
          className="text-[10px] text-text-dim hover:text-text"
        >
          {jumpLabel ?? '→'}
        </button>
      ) : null}
    </div>
  );
}

function uptimeFmt(s: number | undefined): string {
  if (!s) return '–';
  const d = Math.floor(s / 86400);
  return d > 0 ? `${d}d` : `${Math.floor(s / 3600)}h`;
}

function TasksRibbon({ hostId }: { hostId: string }) {
  const q = useQuery<TasksPage>({
    queryKey: ['hosts', hostId, 'tasks'],
    queryFn: () => apiFetch<TasksPage>(`/v1/tasks?host_id=${encodeURIComponent(hostId)}&limit=50`),
  });

  if (q.isLoading) return <div className="text-text-dim">…</div>;
  if (q.isError) return <div className="text-red-300">failed</div>;

  const items = q.data?.items ?? [];
  const displayed = items.slice(0, 3);

  if (displayed.length === 0) return <div className="text-text-dim">none</div>;

  return (
    <div className="flex flex-col gap-1">
      {displayed.map(t => (
        <div key={t.id} className="text-text-dim truncate">
          {t.summary ?? t.kind}
        </div>
      ))}
    </div>
  );
}

function AuditRibbon({ hostId }: { hostId: string }) {
  const q = useQuery<AuditPage>({
    queryKey: ['hosts', hostId, 'audit'],
    queryFn: () =>
      apiFetch<AuditPage>(`/v1/audit?subject=${encodeURIComponent(hostId)}&limit=50`),
  });

  if (q.isLoading) return <div className="text-text-dim">…</div>;
  if (q.isError) return <div className="text-red-300">failed</div>;

  const items = q.data?.items ?? [];
  const displayed = items.slice(0, 3);

  if (displayed.length === 0) return <div className="text-text-dim">none</div>;

  return (
    <div className="flex flex-col gap-1">
      {displayed.map(e => (
        <div key={e.sequence} className="text-text-dim truncate text-xs">
          {e.actor} {e.action} {e.subject || '—'}
        </div>
      ))}
    </div>
  );
}

function PostureRibbon({ hostId }: { hostId: string }) {
  const q = useQuery<PostureResponse>({
    queryKey: ['hosts', hostId, 'posture'],
    queryFn: () =>
      apiFetch<PostureResponse>(
        `/v1/posture?subject_kind=host&subject_id=${encodeURIComponent(hostId)}`,
      ),
  });

  if (q.isLoading) return <div className="text-text-dim">…</div>;
  if (q.isError) return <div className="text-red-300">failed</div>;

  const items = q.data?.findings ?? [];
  const displayed = items.slice(0, 5);

  if (displayed.length === 0) return <div className="text-text-dim">none</div>;

  return (
    <div className="flex flex-col gap-1">
      {displayed.map(f => (
        <div key={f.id} className="text-text-dim truncate text-xs">
          [{f.severity}] {f.title}
        </div>
      ))}
    </div>
  );
}

export function OverviewDashboard({ host, onJump }: Props) {
  const labelKeys = Object.values(host.labels ?? {});
  return (
    <div className="space-y-3 text-sm">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <Kpi
          label="Status"
          value={host.status === 'healthy' ? 'Healthy' : host.status}
          sub={host.last_seen_at ? new Date(host.last_seen_at).toLocaleTimeString() : ''}
        />
        <Kpi label="CPU" value={host.cpu_pct != null ? `${host.cpu_pct}%` : '–'} />
        <Kpi label="Mem" value={host.mem_pct != null ? `${host.mem_pct}%` : '–'} />
        <Kpi label="Disk" value={host.disk_pct != null ? `${host.disk_pct}%` : '–'} />
        <Kpi label="Net" value="–" sub="rx/tx" />
        <Kpi label="Uptime" value={uptimeFmt(host.uptime_s)} />
      </div>

      <div className="grid gap-3 lg:grid-cols-[1.2fr_1fr]">
        <div>
          <SectionHeader title="Identity" />
          <div className="rounded border border-hairline bg-surface-2 p-2 text-xs text-text-dim">
            {host.hostname} · {host.os ?? '–'} {host.os_version ?? ''} · {host.arch ?? ''} · kernel {host.kernel ?? '–'}
            <div className="mt-1 flex flex-wrap gap-1">
              {labelKeys.map(l => (
                <span key={l} className="rounded bg-surface px-2 text-[10px] text-text">
                  {l}
                </span>
              ))}
            </div>
          </div>

          <SectionHeader title="Active tasks" onJump={() => onJump('tasks')} jumpLabel="Tasks →" />
          <div className="rounded border border-hairline bg-surface-2 p-2 text-xs text-text-dim">
            <TasksRibbon hostId={host.id} />
          </div>

          <SectionHeader title="Audit" onJump={() => onJump('audit')} jumpLabel="Audit →" />
          <div className="rounded border border-hairline bg-surface-2 p-2 text-xs text-text-dim">
            <AuditRibbon hostId={host.id} />
          </div>
        </div>

        <div>
          <SectionHeader title="Posture" onJump={() => onJump('posture')} jumpLabel="Posture →" />
          <div className="rounded border border-hairline bg-surface-2 p-2 text-xs text-text-dim">
            <PostureRibbon hostId={host.id} />
          </div>

          <SectionHeader title="Advisories" onJump={() => onJump('advisories')} jumpLabel="Advisories →" />
          <div className="rounded border border-hairline bg-surface-2 p-2 text-xs text-text-dim">
            none
          </div>
        </div>
      </div>
    </div>
  );
}
