'use client';

import { useState } from 'react';
import type { Host } from '@/lib/api/hosts';
import { HostTerminalPanel } from '@/components/hosts/host-terminal-panel';
import { PaneChrome, type PaneAction, type PaneTab } from './pane-chrome';
import { QuickActions } from './quick-actions';
import { HostLogsPanel } from './host-logs-panel';
import { HostFilesPanel } from './host-files-panel';

export type ActionMode = 'quick' | 'term' | 'logs' | 'files' | 'trust';

const TABS: PaneTab[] = [
  { key: 'quick', label: 'Quick', hotkey: 'q' },
  { key: 'term', label: 'Terminal', hotkey: 'w' },
  { key: 'logs', label: 'Logs', hotkey: 'e' },
  { key: 'files', label: 'Files', hotkey: 'r' },
  { key: 'trust', label: 'Trust', hotkey: 't' },
];

interface Props {
  host: Host;
  mode: ActionMode;
  onModeChange: (m: ActionMode) => void;
}

export function ActionPane({ host, mode, onModeChange }: Props) {
  const [paused, setPaused] = useState(false);
  const [wrap, setWrap] = useState(true);

  const actions: PaneAction[] =
    mode === 'logs'
      ? [
          {
            icon: paused ? '▶' : '‖',
            label: paused ? 'Resume tail' : 'Pause tail',
            onClick: () => setPaused(p => !p),
          },
          {
            icon: '↩',
            label: 'Toggle wrap',
            onClick: () => setWrap(w => !w),
          },
        ]
      : [];

  return (
    <PaneChrome
      label="Action"
      tabs={TABS}
      value={mode}
      onChange={k => onModeChange(k as ActionMode)}
      actions={actions}
    >
      {mode === 'quick' ? <QuickActions host={host} /> : null}
      {mode === 'term' ? <HostTerminalPanel hostId={host.id} /> : null}
      {mode === 'logs' ? (
        <HostLogsPanel hostId={host.id} paused={paused} wrap={wrap} severity="all" />
      ) : null}
      {mode === 'files' ? <HostFilesPanel hostId={host.id} /> : null}
      {mode === 'trust' ? (
        <div className="text-sm text-text-dim">
          Trust info for host {host.id}.<br />
          Trust API not yet wired; placeholder pending backend endpoint.
        </div>
      ) : null}
    </PaneChrome>
  );
}
