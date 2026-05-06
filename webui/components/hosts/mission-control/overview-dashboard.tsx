'use client';

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
            (live task ribbon — wired in next task)
          </div>

          <SectionHeader title="Audit" onJump={() => onJump('audit')} jumpLabel="Audit →" />
          <div className="rounded border border-hairline bg-surface-2 p-2 text-xs text-text-dim">
            (recent events — wired in next task)
          </div>
        </div>

        <div>
          <SectionHeader title="Posture" onJump={() => onJump('posture')} jumpLabel="Posture →" />
          <div className="rounded border border-hairline bg-surface-2 p-2 text-xs text-text-dim">
            (top posture checks — wired in next task)
          </div>

          <SectionHeader title="Advisories" onJump={() => onJump('advisories')} jumpLabel="Advisories →" />
          <div className="rounded border border-hairline bg-surface-2 p-2 text-xs text-text-dim">
            (CVE list — wired in next task)
          </div>
        </div>
      </div>
    </div>
  );
}
