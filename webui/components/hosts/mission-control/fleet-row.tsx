'use client';

import type { Host } from '@/lib/api/hosts';
import type { Density } from '@/lib/mission-control/density';

interface Props {
  host: Host;
  density: Density;
  selected: boolean;
  onSelect: (id: string) => void;
  cpuHistory?: number[];
}

const DOT: Record<Host['status'], string> = {
  healthy: 'bg-green-500',
  warning: 'bg-yellow-500',
  critical: 'bg-red-500',
  offline: 'bg-text-dim',
  pending: 'bg-accent',
};

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) return null;
  const max = Math.max(...data, 1);
  const points = data
    .map((v, i) => `${(i / (data.length - 1)) * 60},${18 - (v / max) * 16}`)
    .join(' ');
  return (
    <svg width="60" height="18" viewBox="0 0 60 18" aria-hidden="true">
      <title>CPU history sparkline</title>
      <polyline fill="none" stroke={color} strokeWidth="1" points={points} />
    </svg>
  );
}

function Bar({ pct, tone }: { pct: number; tone: 'ok' | 'warn' | 'crit' }) {
  const color = tone === 'crit' ? 'bg-red-500' : tone === 'warn' ? 'bg-yellow-500' : 'bg-green-500';
  return (
    <div className="h-[3px] flex-1 overflow-hidden rounded bg-surface-2">
      <div className={color} style={{ width: `${Math.min(100, Math.max(0, pct))}%`, height: '100%' }} />
    </div>
  );
}

function tone(pct: number): 'ok' | 'warn' | 'crit' {
  if (pct >= 85) return 'crit';
  if (pct >= 70) return 'warn';
  return 'ok';
}

export function FleetRow({ host, density, selected, onSelect, cpuHistory }: Props) {
  const name = host.display_name ?? host.hostname;
  const dot = DOT[host.status];
  const isOffline = host.status === 'offline';

  return (
    // biome-ignore lint/a11y/useSemanticElements: custom listbox item
    <button
      role="option"
      aria-selected={selected}
      onClick={() => onSelect(host.id)}
      className={`w-full cursor-pointer rounded px-2 py-1.5 text-sm text-left ${
        selected ? 'bg-accent/10 ring-1 ring-accent' : 'hover:bg-surface-2'
      }`}
      type="button"
    >
      <div className="flex items-center gap-2">
        <span className={`inline-block h-2 w-2 rounded-full ${dot}`} aria-hidden />
        <span className="truncate font-medium text-text">{name}</span>
        {density !== 'lean' && host.os ? (
          <span className="rounded bg-surface-2 px-1.5 text-[10px] text-text-dim">{host.os}</span>
        ) : null}
      </div>

      {density !== 'lean' ? (
        <div className="mt-1 text-[11px] text-text-dim">
          {isOffline
            ? `offline · ${host.last_seen_at ? new Date(host.last_seen_at).toLocaleTimeString() : 'never'}`
            : `cpu ${host.cpu_pct ?? '–'}% · mem ${host.mem_pct ?? '–'}%`}
        </div>
      ) : null}

      {density === 'balanced' && !isOffline && host.cpu_pct != null && host.mem_pct != null ? (
        <div className="mt-1 flex gap-1">
          <Bar pct={host.cpu_pct} tone={tone(host.cpu_pct)} />
          <Bar pct={host.mem_pct} tone={tone(host.mem_pct)} />
        </div>
      ) : null}

      {density === 'rich' && cpuHistory && cpuHistory.length > 1 ? (
        <Sparkline data={cpuHistory} color="rgb(74 168 138)" />
      ) : null}
    </button>
  );
}
