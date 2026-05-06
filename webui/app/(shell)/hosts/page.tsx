'use client';

export const dynamic = 'force-dynamic';

import { useState } from 'react';
import { HostFilters } from '@/components/hosts/host-filters';
import { HostListTable } from '@/components/hosts/host-list-table';
import { EnrollmentModal } from '@/components/hosts/enrollment-modal';
import { useCanPerform } from '@/lib/rbac';

export default function HostsPage() {
  const [status, setStatus] = useState('all');
  const [search, setSearch] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const canMint = useCanPerform('mint-enrollment-token');

  return (
    <div className="p-4">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-h2 font-bold text-text mb-2">Hosts</h1>
          <p className="text-text-dim">Manage infrastructure endpoints</p>
        </div>
        <button
          type="button"
          disabled={!canMint.allowed}
          title={canMint.allowed ? '' : canMint.reason}
          onClick={() => setModalOpen(true)}
          className="rounded bg-accent px-3 py-2 text-sm font-medium text-black disabled:cursor-not-allowed disabled:opacity-50"
        >
          Enroll host
        </button>
      </div>

      <HostFilters onStatusChange={setStatus} onSearch={setSearch} />
      <HostListTable status={status} search={search} onEnroll={() => setModalOpen(true)} />

      {modalOpen ? <EnrollmentModal onClose={() => setModalOpen(false)} /> : null}
    </div>
  );
}
