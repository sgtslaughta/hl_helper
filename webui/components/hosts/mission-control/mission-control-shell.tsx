'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { EnrollmentModal } from '@/components/hosts/enrollment-modal';
import { type Host, getHost, listHosts } from '@/lib/api/hosts';
import { type PendingToken, listPendingTokens } from '@/lib/api/enrollment';
import { ActionPane, type ActionMode } from './action-pane';
import { FleetRail } from './fleet-rail';
import { FocusPane } from './focus-pane';
import type { FocusMode } from './overview-dashboard';
import { TopBar, type FleetCounts } from './top-bar';

const FOCUS_KEYS: Record<string, FocusMode> = {
  '1': 'overview',
  '2': 'posture',
  '3': 'audit',
  '4': 'tasks',
};
const ACTION_KEYS: Record<string, ActionMode> = {
  q: 'quick',
  w: 'term',
  e: 'logs',
  r: 'files',
  t: 'trust',
};

export function MissionControlShell({ initialHostId }: { initialHostId: string | null }) {
  const router = useRouter();
  const pathname = usePathname();
  const [selectedId, setSelectedId] = useState<string | null>(initialHostId);
  const [focusMode, setFocusMode] = useState<FocusMode>('overview');
  const [actionMode, setActionMode] = useState<ActionMode>('quick');
  const [enrollOpen, setEnrollOpen] = useState(false);

  useEffect(() => {
    const target = selectedId ? `/hosts/${selectedId}` : '/hosts';
    if (pathname !== target) router.replace(target);
  }, [selectedId, pathname, router]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (document.activeElement as HTMLElement | null)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (FOCUS_KEYS[e.key]) {
        e.preventDefault();
        setFocusMode(FOCUS_KEYS[e.key]);
        return;
      }
      if (ACTION_KEYS[e.key]) {
        e.preventDefault();
        setActionMode(ACTION_KEYS[e.key]);
        return;
      }
      if ((e.key === 'e' || e.key === 'E') && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setEnrollOpen(true);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (selectedId) setFocusMode('overview');
  }, [selectedId]);

  const hostsQ = useQuery<Host[]>({ queryKey: ['hosts'], queryFn: () => listHosts({}) });
  const pendingQ = useQuery<PendingToken[]>({
    queryKey: ['enrollment-tokens'],
    queryFn: listPendingTokens,
  });
  const focusedQ = useQuery<Host>({
    queryKey: ['hosts', selectedId],
    queryFn: () => getHost(selectedId as string),
    enabled: !!selectedId,
  });

  const counts: FleetCounts = useMemo(() => {
    const out: FleetCounts = { critical: 0, pending: pendingQ.data?.length ?? 0, online: 0, offline: 0 };
    for (const h of hostsQ.data ?? []) {
      if (h.status === 'critical' || h.status === 'warning') out.critical++;
      else if (h.status === 'offline') out.offline++;
      else out.online++;
    }
    return out;
  }, [hostsQ.data, pendingQ.data]);

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col gap-2 p-2">
      <TopBar counts={counts} onEnroll={() => setEnrollOpen(true)} onPalette={() => {}} />
      <div className="flex flex-1 gap-2 overflow-hidden">
        <FleetRail selectedId={selectedId} onSelect={setSelectedId} />
        <div className="min-w-0 flex-1">
          {focusedQ.data ? (
            <FocusPane host={focusedQ.data} mode={focusMode} onModeChange={setFocusMode} />
          ) : (
            <div className="flex h-full items-center justify-center rounded border border-hairline bg-surface text-text-dim">
              Select a host to focus.
            </div>
          )}
        </div>
        <div className="w-[380px] shrink-0">
          {focusedQ.data ? (
            <ActionPane host={focusedQ.data} mode={actionMode} onModeChange={setActionMode} />
          ) : (
            <div className="flex h-full items-center justify-center rounded border border-hairline bg-surface text-text-dim">
              No host selected.
            </div>
          )}
        </div>
      </div>
      {enrollOpen ? <EnrollmentModal onClose={() => setEnrollOpen(false)} /> : null}
    </div>
  );
}
