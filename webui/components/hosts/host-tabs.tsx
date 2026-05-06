'use client';

import { useState, type ReactNode } from 'react';

type TabKey = 'overview' | 'tasks' | 'posture' | 'terminal' | 'audit';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'tasks', label: 'Tasks' },
  { key: 'posture', label: 'Posture' },
  { key: 'terminal', label: 'Terminal' },
  { key: 'audit', label: 'Audit' },
];

export function HostTabs({ panels }: { panels: Record<TabKey, ReactNode> }) {
  const [active, setActive] = useState<TabKey>('overview');
  return (
    <div>
      <nav role="tablist" className="flex border-b border-hairline">
        {TABS.map(t => (
          <button
            key={t.key}
            role="tab"
            aria-selected={active === t.key}
            onClick={() => setActive(t.key)}
            className={`px-4 py-2 text-sm ${active === t.key ? 'border-b-2 border-accent text-text' : 'text-text-dim hover:text-text'}`}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <div role="tabpanel" className="pt-4">{panels[active]}</div>
    </div>
  );
}
