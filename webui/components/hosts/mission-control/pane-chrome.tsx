'use client';

import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import type { ReactNode } from 'react';

export type PillTone = 'info' | 'warn' | 'crit' | 'ok';

export interface PaneTab {
  key: string;
  label: string;
  hotkey?: string;
  pill?: { text: string; tone: PillTone };
  overflow?: boolean;
}

export interface PaneAction {
  icon: ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}

interface Props {
  label: string;
  tabs: PaneTab[];
  value: string;
  onChange: (key: string) => void;
  actions: PaneAction[];
  children: ReactNode;
}

const TONE_CLASS: Record<PillTone, string> = {
  info: 'bg-accent/20 text-accent',
  warn: 'bg-yellow-500/20 text-yellow-300',
  crit: 'bg-red-500/20 text-red-300',
  ok: 'bg-green-500/20 text-green-300',
};

export function PaneChrome({ label, tabs, value, onChange, actions, children }: Props) {
  const primary = tabs.filter(t => !t.overflow);
  const overflow = tabs.filter(t => t.overflow);
  const active = tabs.find(t => t.key === value);
  const activeOverflow = overflow.find(t => t.key === value);

  return (
    <section className="flex h-full flex-col rounded border border-hairline bg-surface" aria-label={label}>
      <header className="flex items-center justify-between border-b border-hairline px-2">
        <div role="tablist" className="flex">
          {primary.map(t => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={value === t.key}
              onClick={() => onChange(t.key)}
              className={`flex items-center gap-2 px-3 py-2 text-sm border-b-2 ${
                value === t.key
                  ? 'border-accent text-text'
                  : 'border-transparent text-text-dim hover:text-text'
              }`}
            >
              <span>{t.label}</span>
              {t.hotkey ? (
                <span className="rounded border border-hairline bg-surface-2 px-1 text-[10px] text-text-dim">
                  {t.hotkey}
                </span>
              ) : null}
              {t.pill ? (
                <span
                  data-tone={t.pill.tone}
                  className={`rounded-full px-2 text-[10px] ${TONE_CLASS[t.pill.tone]}`}
                >
                  {t.pill.text}
                </span>
              ) : null}
            </button>
          ))}
          {overflow.length > 0 ? (
            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <button
                  type="button"
                  className={`px-3 py-2 text-sm border-b-2 ${
                    activeOverflow ? 'border-accent text-text' : 'border-transparent text-text-dim hover:text-text'
                  }`}
                  aria-label={activeOverflow ? `${activeOverflow.label} (more tabs)` : 'More tabs'}
                >
                  {activeOverflow ? `${activeOverflow.label} ▾` : 'More ▾'}
                </button>
              </DropdownMenu.Trigger>
              <DropdownMenu.Content
                align="start"
                className="rounded border border-hairline bg-surface-2 py-1 text-sm"
              >
                {overflow.map(t => (
                  <DropdownMenu.Item
                    key={t.key}
                    onSelect={() => onChange(t.key)}
                    className="cursor-pointer px-3 py-1 text-text-dim hover:bg-surface hover:text-text"
                  >
                    {t.label}
                  </DropdownMenu.Item>
                ))}
              </DropdownMenu.Content>
            </DropdownMenu.Root>
          ) : null}
        </div>
        <div className="flex items-center gap-1">
          {actions.map(a => (
            <button
              key={a.label}
              type="button"
              aria-label={a.label}
              title={a.label}
              disabled={a.disabled}
              onClick={a.onClick}
              className="flex h-7 w-7 items-center justify-center rounded text-text-dim hover:bg-surface-2 hover:text-text disabled:opacity-40"
            >
              {a.icon}
            </button>
          ))}
        </div>
      </header>
      <div role="tabpanel" aria-label={active?.label ?? label} className="flex-1 overflow-auto p-3">
        {children}
      </div>
    </section>
  );
}
