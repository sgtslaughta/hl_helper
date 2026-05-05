'use client';

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { mintEnrollmentToken, revokePendingToken, type MintResponse } from '@/lib/api/enrollment';
import { RiskBadge } from '@/components/primitives/risk-badge';
import { Disclosure } from '@/components/primitives/disclosure';
import { Countdown } from '@/components/primitives/countdown';

interface Props {
  onClose: () => void;
}

type Step = 'mint' | 'install';

const TTL_OPTIONS: { label: string; value: number }[] = [
  { label: '5 minutes', value: 300 },
  { label: '15 minutes', value: 900 },
  { label: '1 hour', value: 3600 },
  { label: '24 hours', value: 86_400 },
];

export function EnrollmentModal({ onClose }: Props) {
  const qc = useQueryClient();
  const [step, setStep] = useState<Step>('mint');
  const [label, setLabel] = useState('');
  const [ttl, setTtl] = useState<number>(900);
  const [minted, setMinted] = useState<MintResponse | null>(null);

  const mintMut = useMutation({
    mutationFn: () => mintEnrollmentToken({ label, ttl_seconds: ttl }),
    onSuccess: (data) => {
      setMinted(data);
      setStep('install');
      qc.invalidateQueries({ queryKey: ['enrollment-tokens'] });
    },
  });

  const revokeMut = useMutation({
    mutationFn: (tokenId: string) => revokePendingToken(tokenId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['enrollment-tokens'] });
      onClose();
    },
  });

  return (
    <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-lg rounded border border-hairline bg-surface p-5">
        <header className="mb-3 flex items-center justify-between">
          <h2 className="text-h3 font-bold text-text">Enroll a host</h2>
          <RiskBadge variant="caution" />
        </header>

        {step === 'mint' ? (
          <div className="space-y-3">
            <p className="text-sm text-text-dim">
              An enrollment token authorizes one host to register itself. Treat the token as a secret.
            </p>
            <label className="block text-sm">
              Label
              <input
                type="text"
                value={label}
                onChange={e => setLabel(e.target.value)}
                placeholder="lab-router-01"
                className="mt-1 w-full rounded border border-hairline bg-surface-2 px-2 py-1 text-text"
                aria-label="label"
              />
            </label>
            <label className="block text-sm">
              Expires in
              <select
                value={ttl}
                onChange={e => setTtl(Number(e.target.value))}
                className="mt-1 w-full rounded border border-hairline bg-surface-2 px-2 py-1 text-text"
              >
                {TTL_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </label>
            <Disclosure label="What is an enrollment token?" storageKey="enroll-explain">
              <ul className="list-disc space-y-1 pl-5 text-sm">
                <li>Single-use: redemption invalidates it.</li>
                <li>Server stores only a hash; the plaintext is shown once.</li>
                <li>Revoke at any time before redemption.</li>
              </ul>
            </Disclosure>
            <footer className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={onClose} className="rounded border border-hairline px-3 py-1.5 text-sm text-text hover:bg-surface-2">Cancel</button>
              <button
                type="button"
                disabled={label.trim().length === 0 || mintMut.isPending}
                onClick={() => mintMut.mutate()}
                className="rounded bg-accent px-3 py-1.5 text-sm font-medium text-black disabled:opacity-50"
              >
                Mint token
              </button>
            </footer>
          </div>
        ) : null}

        {step === 'install' && minted ? (
          <InstallStep
            minted={minted}
            onDone={onClose}
            onRevoke={() => revokeMut.mutate(minted.token_id)}
          />
        ) : null}
      </div>
    </div>
  );
}

function InstallStep({
  minted,
  onDone,
  onRevoke,
}: {
  minted: MintResponse;
  onDone: () => void;
  onRevoke: () => void;
}) {
  function copy() {
    void navigator.clipboard.writeText(minted.install_command);
  }
  return (
    <div className="space-y-3">
      <p className="text-sm text-text-dim">Run this command on the host you want to enroll.</p>
      <div className="rounded border border-hairline bg-surface-2 p-2 font-mono text-xs">
        <pre className="overflow-auto whitespace-pre-wrap break-all">{minted.install_command}</pre>
      </div>
      <div className="flex items-center gap-3 text-sm">
        <button type="button" onClick={copy} className="rounded border border-hairline px-2 py-1 text-text hover:bg-surface-2">Copy command</button>
        <span className="text-text-dim">Expires in <Countdown to={minted.expires_at} /></span>
      </div>
      <Disclosure label="What this does" storageKey="enroll-what">
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>Downloads the agent binary signed by this server.</li>
          <li>Generates an Ed25519 keypair on the host.</li>
          <li>Submits a CSR to <code>POST /v1/enroll</code>.</li>
          <li>Server issues a leaf cert; the host appears in the list.</li>
        </ul>
      </Disclosure>
      <Disclosure label="Risks" storageKey="enroll-risks">
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>Anyone holding the token before expiry can enroll a host.</li>
          <li>Revoke immediately if the token is exposed.</li>
          <li>The token is single-use; redemption invalidates it.</li>
        </ul>
      </Disclosure>
      <footer className="flex justify-between gap-2 pt-2">
        <button type="button" onClick={onRevoke} className="rounded border border-red-500/40 px-3 py-1.5 text-sm text-red-400 hover:bg-red-500/10">Revoke token</button>
        <button type="button" onClick={onDone} className="rounded bg-accent px-3 py-1.5 text-sm font-medium text-black">Done</button>
      </footer>
    </div>
  );
}
