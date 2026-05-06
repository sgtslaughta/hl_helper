'use client';

import Link from 'next/link';
import type { Host } from '@/lib/api/hosts';

const STATUS_COLORS: Record<Host['status'], string> = {
  healthy: 'text-green-400',
  warning: 'text-yellow-400',
  critical: 'text-red-400',
  offline: 'text-text-dim',
  pending: 'text-yellow-400',
};

export function ActiveHostRow({ host }: { host: Host }) {
  return (
    <tr className="border-b border-hairline hover:bg-surface-2">
      <td className="px-4 py-2 text-text">
        <Link href={`/hosts/${host.id}`} className="hover:underline">
          {host.display_name ?? host.hostname}
        </Link>
      </td>
      <td className="px-4 py-2 text-text-dim">{host.labels?.os ?? '—'}</td>
      <td className="px-4 py-2 text-text-dim">{host.labels?.version ?? '—'}</td>
      <td className={`px-4 py-2 ${STATUS_COLORS[host.status]}`}>{host.status}</td>
      <td className="px-4 py-2 text-text-dim">{host.last_seen_at ?? '—'}</td>
      <td className="px-4 py-2 text-right text-text-dim">…</td>
    </tr>
  );
}
