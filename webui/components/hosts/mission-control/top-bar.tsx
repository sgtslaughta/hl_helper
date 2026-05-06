'use client';

import { useCanPerform } from '@/lib/rbac';

export interface FleetCounts {
  critical: number;
  pending: number;
  online: number;
  offline: number;
}

interface Props {
  counts: FleetCounts;
  onEnroll: () => void;
  onPalette: () => void;
  onPillClick?: (group: keyof FleetCounts) => void;
}

const TONE: Record<keyof FleetCounts, string> = {
  critical: 'bg-red-500/15 text-red-300 hover:bg-red-500/25',
  pending: 'bg-yellow-500/15 text-yellow-300 hover:bg-yellow-500/25',
  online: 'bg-green-500/15 text-green-300 hover:bg-green-500/25',
  offline: 'bg-text-dim/20 text-text-dim hover:bg-text-dim/30',
};

const GROUPS: (keyof FleetCounts)[] = ['critical', 'pending', 'online', 'offline'];

export function TopBar({ counts, onEnroll, onPalette, onPillClick }: Props) {
  const canMint = useCanPerform('mint-enrollment-token');
  return (
    <header className="flex items-center justify-between gap-4 rounded border border-hairline bg-surface px-3 py-2">
      <div className="flex items-center gap-2">
        <h1 className="text-h3 font-bold text-text">Hosts</h1>
        {GROUPS.map(g => (
          <button
            key={g}
            type="button"
            onClick={() => onPillClick?.(g)}
            className={`rounded-full px-2 py-0.5 text-xs ${TONE[g]}`}
          >
            {counts[g]} {g}
          </button>
        ))}
      </div>
      <button
        type="button"
        aria-label="Open palette"
        onClick={onPalette}
        className="max-w-md flex-1 rounded border border-hairline bg-surface-2 px-3 py-1.5 text-left text-sm text-text-dim hover:text-text"
      >
        ⌘K  search hosts, run command, jump…
      </button>
      <button
        type="button"
        disabled={!canMint.allowed}
        title={canMint.allowed ? 'Enroll host (⌘E)' : (canMint.reason ?? 'Not allowed')}
        onClick={onEnroll}
        className="rounded bg-accent px-3 py-1.5 text-sm font-medium text-black disabled:cursor-not-allowed disabled:opacity-50"
      >
        + Enroll host
      </button>
    </header>
  );
}
