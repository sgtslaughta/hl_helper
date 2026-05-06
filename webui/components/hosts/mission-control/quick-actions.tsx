'use client';

import { type ReactNode, useEffect, useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ActionConfirmDialog } from '@/components/hosts/action-confirm-dialog';
import { type Host, pkgUpdateHost, rebootHost, revokeHostCert, shellExecHost } from '@/lib/api/hosts';
import { type CanPerform, useCanPerform } from '@/lib/rbac';
import type { ActionType } from '@/lib/risk-catalog';

interface ActionDef {
  type: ActionType;
  short: string;
  label: string;
  desc: string;
  danger?: boolean;
}

const ACTIONS: ActionDef[] = [
  { type: 'reboot', short: 'REBOOT', label: 'Reboot', desc: 'graceful' },
  { type: 'shell-exec', short: 'SHELL', label: 'Run shell', desc: 'open prompt' },
  { type: 'pkg-update', short: 'PATCH', label: 'Patch', desc: 'apt upgrade' },
  { type: 'revoke-host', short: 'REVOKE', label: 'Revoke trust', desc: 'offboard', danger: true },
];

export function QuickActions({ host }: { host: Host }) {
  const [pending, setPending] = useState<ActionType | null>(null);
  const [command, setCommand] = useState('');
  const [timeout_s, setTimeout_s] = useState(60);
  const [classes, setClasses] = useState<string[]>(['security']);
  const [reason, setReason] = useState('');
  const qc = useQueryClient();

  // biome-ignore lint/correctness/useExhaustiveDependencies: setters are stable
  useEffect(() => {
    setCommand('');
    setTimeout_s(60);
    setClasses(['security']);
    setReason('');
  }, [pending]);

  const reboot = useCanPerform('reboot');
  const shellExec = useCanPerform('shell-exec');
  const pkgUpdate = useCanPerform('pkg-update');
  const revoke = useCanPerform('revoke-host');

  const caps: Record<ActionType, CanPerform> = useMemo(
    () => ({
      reboot,
      'shell-exec': shellExec,
      'pkg-update': pkgUpdate,
      'revoke-host': revoke,
      'delete-host': { allowed: false },
      'mint-enrollment-token': { allowed: false },
      'revoke-enrollment-token': { allowed: false },
    }),
    [reboot, shellExec, pkgUpdate, revoke],
  );

  const rebootMut = useMutation({
    mutationFn: (principal: string) => rebootHost(host.id, { delay_s: 0, reason: '' }, principal),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hosts', host.id, 'tasks'] }),
  });
  const shellMut = useMutation({
    mutationFn: (principal: string) => shellExecHost(host.id, { command, timeout_s }, principal),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hosts', host.id] }),
  });
  const pkgMut = useMutation({
    mutationFn: (principal: string) => pkgUpdateHost(host.id, { classes }, principal),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hosts', host.id] }),
  });
  const revokeMut = useMutation({
    mutationFn: (principal: string) => revokeHostCert(host.id, { reason }, principal),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hosts'] }),
  });

  function dispatch(action: ActionType, principal: string) {
    if (action === 'reboot') rebootMut.mutate(principal);
    else if (action === 'shell-exec') shellMut.mutate(principal);
    else if (action === 'pkg-update') pkgMut.mutate(principal);
    else if (action === 'revoke-host') revokeMut.mutate(principal);
    setPending(null);
  }

  function formChildren(): ReactNode {
    if (pending === 'shell-exec') {
      return (
        <div className="mb-3 space-y-2">
          <label className="block text-sm font-medium text-text">
            Command
            <input
              type="text"
              value={command}
              onChange={e => setCommand(e.target.value)}
              className="mt-1 w-full rounded border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-text"
            />
          </label>
          <label className="block text-sm font-medium text-text">
            Timeout (s)
            <input
              type="number"
              min={1}
              value={timeout_s}
              onChange={e => setTimeout_s(Math.max(1, Number.parseInt(e.target.value) || 1))}
              className="mt-1 w-full rounded border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-text"
            />
          </label>
        </div>
      );
    }
    if (pending === 'pkg-update') {
      return (
        <fieldset className="mb-3">
          <legend className="text-sm font-medium text-text">Update classes</legend>
          {['security', 'bugfix', 'enhancement'].map(opt => (
            <label key={opt} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={classes.includes(opt)}
                onChange={e =>
                  setClasses(prev => (e.target.checked ? [...prev, opt] : prev.filter(c => c !== opt)))
                }
              />
              {opt}
            </label>
          ))}
        </fieldset>
      );
    }
    if (pending === 'revoke-host') {
      return (
        <label className="mb-3 block text-sm font-medium text-text">
          Reason
          <textarea
            value={reason}
            onChange={e => setReason(e.target.value)}
            rows={3}
            className="mt-1 w-full rounded border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-text"
          />
        </label>
      );
    }
    return null;
  }

  const pendingCap = pending ? caps[pending] : null;

  return (
    <>
      <div className="grid grid-cols-2 gap-2">
        {ACTIONS.map(a => {
          const cap = caps[a.type];
          return (
            <button
              key={a.type}
              type="button"
              disabled={!cap.allowed}
              title={cap.allowed ? a.label : (cap.reason ?? '')}
              onClick={() => setPending(a.type)}
              className={`flex flex-col items-start gap-0.5 rounded border p-2 text-left text-sm hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-40 ${
                a.danger
                  ? 'border-red-500/30 text-red-300 hover:bg-red-500/10'
                  : 'border-hairline'
              }`}
            >
              <span className="text-[10px] uppercase tracking-wide text-text-dim">{a.short}</span>
              <span>{a.label}</span>
              <span className="text-[10px] text-text-dim">{a.desc}</span>
            </button>
          );
        })}
      </div>
      {pending && pendingCap ? (
        <ActionConfirmDialog
          action={pending}
          host={{ id: host.id, hostname: host.hostname }}
          principal={pendingCap.principal ?? ''}
          onClose={() => setPending(null)}
          onConfirm={() => dispatch(pending, pendingCap.principal ?? '')}
          formChildren={formChildren()}
        />
      ) : null}
    </>
  );
}
