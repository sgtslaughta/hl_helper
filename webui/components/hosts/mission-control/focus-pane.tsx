'use client';

import type { Host } from '@/lib/api/hosts';
import { HostAuditPanel } from '@/components/hosts/host-audit-panel';
import { HostPosturePanel } from '@/components/hosts/host-posture-panel';
import { HostTasksPanel } from '@/components/hosts/host-tasks-panel';
import { OverviewDashboard, type FocusMode } from './overview-dashboard';
import { PaneChrome, type PaneTab } from './pane-chrome';

const TABS: PaneTab[] = [
  { key: 'overview', label: 'Overview', hotkey: '1' },
  { key: 'posture', label: 'Posture', hotkey: '2' },
  { key: 'audit', label: 'Audit', hotkey: '3' },
  { key: 'tasks', label: 'Tasks', hotkey: '4' },
  { key: 'advisories', label: 'Advisories', overflow: true },
  { key: 'labels', label: 'Labels', overflow: true },
  { key: 'files', label: 'Files', overflow: true },
];

interface Props {
  host: Host;
  mode: FocusMode;
  onModeChange: (m: FocusMode) => void;
}

export function FocusPane({ host, mode, onModeChange }: Props) {
  return (
    <PaneChrome
      label="Focus"
      tabs={TABS}
      value={mode}
      onChange={k => onModeChange(k as FocusMode)}
      actions={[]}
    >
      {mode === 'overview' ? <OverviewDashboard host={host} onJump={onModeChange} /> : null}
      {mode === 'posture' ? <HostPosturePanel hostId={host.id} /> : null}
      {mode === 'audit' ? <HostAuditPanel hostId={host.id} /> : null}
      {mode === 'tasks' ? <HostTasksPanel hostId={host.id} /> : null}
      {mode === 'advisories' || mode === 'labels' || mode === 'files' || mode === 'network' || mode === 'updates' ? (
        <div className="text-sm text-text-dim">{mode} view (placeholder).</div>
      ) : null}
    </PaneChrome>
  );
}
