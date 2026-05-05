'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { revokePendingToken, type PendingToken } from '@/lib/api/enrollment';
import { Countdown } from '@/components/primitives/countdown';

export function PendingHostRow({ token }: { token: PendingToken }) {
  const qc = useQueryClient();
  const mut = useMutation({
    mutationFn: () => revokePendingToken(token.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['enrollment-tokens'] }),
  });
  return (
    <tr className="border-b border-hairline bg-yellow-500/5">
      <td className="px-4 py-2 text-text">
        <span className="mr-2 inline-flex items-center rounded bg-yellow-500/15 px-1.5 py-0.5 text-xs text-yellow-400">pending</span>
        {token.label ?? <span className="text-text-dim">(no label)</span>}
      </td>
      <td className="px-4 py-2 text-text-dim">—</td>
      <td className="px-4 py-2 text-text-dim">—</td>
      <td className="px-4 py-2 text-text-dim">awaiting redemption</td>
      <td className="px-4 py-2 text-text-dim"><Countdown to={token.expires_at} /></td>
      <td className="px-4 py-2 text-right">
        <button
          type="button"
          onClick={() => mut.mutate()}
          disabled={mut.isPending}
          className="rounded border border-red-500/40 px-2 py-1 text-xs text-red-400 hover:bg-red-500/10 disabled:opacity-50"
        >
          Revoke
        </button>
      </td>
    </tr>
  );
}
