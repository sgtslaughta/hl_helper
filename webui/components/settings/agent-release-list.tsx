'use client';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';

type Release = {
  id: string;
  version: string;
  channel: string;
  os: string;
  arch: string;
  sha256: string;
  size: number;
  status: 'staged' | 'published' | 'yanked';
  uploaded_at: string;
  uploaded_by: string;
};

export function AgentReleaseList() {
  const { data, refetch, isLoading } = useQuery<{ items: Release[] }>({
    queryKey: ['agent-releases'],
    queryFn: async () => {
      return await apiFetch('/v1/agent-releases');
    },
  });

  if (isLoading) return <div>Loading…</div>;
  if (!data) return <div>No data</div>;

  return (
    <div className="overflow-x-auto rounded border border-hairline">
      <table className="w-full text-sm">
        <thead className="bg-surface-2">
          <tr className="text-left text-text">
            <th className="px-4 py-3 font-semibold">Version</th>
            <th className="px-4 py-3 font-semibold">Channel</th>
            <th className="px-4 py-3 font-semibold">OS/Arch</th>
            <th className="px-4 py-3 font-semibold">Status</th>
            <th className="px-4 py-3 font-semibold">Uploaded</th>
            <th className="px-4 py-3 font-semibold text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map(r => (
            <tr key={r.id} className="border-t">
              <td className="px-4 py-3 font-mono">{r.version}</td>
              <td className="px-4 py-3"><Badge>{r.channel}</Badge></td>
              <td className="px-4 py-3 font-mono">{r.os}/{r.arch}</td>
              <td className="px-4 py-3"><Badge variant={r.status === 'yanked' ? 'danger' : 'default'}>{r.status}</Badge></td>
              <td className="px-4 py-3">{new Date(r.uploaded_at).toLocaleString()}</td>
              <td className="px-4 py-3 text-right">
                {r.status !== 'yanked' && (
                  <Button size="sm" variant="ghost" onClick={async () => {
                    const reason = prompt('Yank reason:');
                    if (!reason) return;
                    await apiFetch(`/v1/agent-releases/${r.id}/yank`, {
                      method: 'POST',
                      body: JSON.stringify({ reason }),
                    });
                    refetch();
                  }}>Yank</Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
